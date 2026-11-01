"""Indexing service: orchestrates embedding generation and Qdrant ingestion."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from qdrant_client import models
from sqlalchemy import select
from sqlalchemy.orm import Session

from lectra_core.config import Settings, get_settings
from lectra_core.db.models import ProcessingStage, Video, VideoChunk
from lectra_core.embeddings.service import EmbeddingService
from lectra_core.logging import get_logger
from lectra_core.repositories import chunk_repository
from lectra_core.vectorstore.qdrant import QdrantVectorStore

logger = get_logger("lectra.vectorstore.service")

STAGE_INDEXING = "INDEXING"


@dataclass
class IndexingResult:
    """Summary of the indexing result for a single video."""

    video_id: str
    youtube_id: str
    chunks_indexed: int
    status: str
    verified_points: int
    error: Optional[str] = None


class IndexingService:
    """Coordinates embedding generation, Qdrant upserts, and durable stage transitions."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        embedding_service: Optional[EmbeddingService] = None,
        vector_store: Optional[QdrantVectorStore] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.embedding_service = embedding_service or EmbeddingService(settings=self.settings)
        self.vector_store = vector_store or QdrantVectorStore(settings=self.settings)

    def _get_or_create_stage(self, session: Session, video_id: str) -> ProcessingStage:
        stage = session.scalars(
            select(ProcessingStage).where(
                ProcessingStage.video_id == video_id,
                ProcessingStage.stage_name == STAGE_INDEXING,
            )
        ).first()

        if stage is None:
            stage = ProcessingStage(
                video_id=video_id,
                stage_name=STAGE_INDEXING,
                status="PENDING",
                attempts=0,
            )
            session.add(stage)
            session.flush()
        return stage

    def construct_payload(self, video: Video, chunk: VideoChunk) -> dict:
        """Build the structured payload for a chunk point."""
        return {
            "chunk_id": chunk.id,
            "video_id": video.id,
            "youtube_id": video.youtube_id,
            "playlist_id": video.playlist_id,
            "title": video.title,
            "chunk_index": chunk.chunk_index,
            "start_seconds": chunk.start_seconds,
            "end_seconds": chunk.end_seconds,
            "duration_seconds": chunk.duration_seconds,
            "text": chunk.text,
            "token_count": chunk.token_count,
            "source_segment_start_index": chunk.source_segment_start_index,
            "source_segment_end_index": chunk.source_segment_end_index,
            "youtube_url": f"https://www.youtube.com/watch?v={video.youtube_id}&t={int(chunk.start_seconds)}",
        }

    def index_video(self, session: Session, video: Video, force: bool = False) -> IndexingResult:
        """Index all chunks of a video into Qdrant idempotently with verification."""
        # Check race condition: video was deleted
        if session.get(Video, video.id) is None:
            logger.info(
                "Video was deleted; skipping indexing", extra={"video_id": video.youtube_id}
            )
            return IndexingResult(
                video_id=video.id,
                youtube_id=video.youtube_id,
                chunks_indexed=0,
                status="DELETED",
                verified_points=0,
            )

        stage = self._get_or_create_stage(session, video.id)
        stage.status = "IN_PROGRESS"
        stage.attempts += 1
        session.flush()

        chunks = chunk_repository.get_by_video_id(session, video.id)
        if not chunks:
            logger.warning(
                "No chunks found to index for video",
                extra={"video_id": video.youtube_id},
            )
            stage.status = "COMPLETED"
            stage.completed_at = datetime.now(timezone.utc)
            session.flush()
            return IndexingResult(
                video_id=video.id,
                youtube_id=video.youtube_id,
                chunks_indexed=0,
                status="COMPLETED",
                verified_points=0,
            )

        try:
            # 1. Ensure collection exists and is valid
            self.vector_store.ensure_collection()

            expected_ids = [c.id for c in chunks]

            # Idempotency guard: if all points already exist and are verified in Qdrant,
            # persist the checkpoint without redundant re-embedding or re-uploading.
            if not force:
                existing_points = self.vector_store.retrieve_points(expected_ids)
                if len(existing_points) == len(expected_ids):
                    logger.info(
                        "All video chunks already verified in Qdrant; skipping re-embedding",
                        extra={"video_id": video.youtube_id, "chunk_count": len(chunks)},
                    )
                    stage.status = "COMPLETED"
                    stage.completed_at = stage.completed_at or datetime.now(timezone.utc)
                    stage.error_category = None
                    stage.error_detail = None

                    video.status = "INDEXED"
                    session.flush()

                    return IndexingResult(
                        video_id=video.id,
                        youtube_id=video.youtube_id,
                        chunks_indexed=len(existing_points),
                        status="COMPLETED",
                        verified_points=len(existing_points),
                    )

            # 2. Generate embeddings using EmbeddingGemma 2
            logger.info(
                "Generating embeddings for video chunks",
                extra={"video_id": video.youtube_id, "chunk_count": len(chunks)},
            )
            vectors = self.embedding_service.embed_chunks(chunks, video.title)

            # 3. Construct point structures
            points = [
                models.PointStruct(
                    id=chunk.id,
                    vector=vector,
                    payload=self.construct_payload(video, chunk),
                )
                for chunk, vector in zip(chunks, vectors)
            ]

            # 4. Check race condition before batch upsert into Qdrant
            if session.get(Video, video.id) is None:
                logger.info(
                    "Video was deleted during embedding; skipping Qdrant upsert",
                    extra={"video_id": video.youtube_id},
                )
                return IndexingResult(
                    video_id=video.id,
                    youtube_id=video.youtube_id,
                    chunks_indexed=0,
                    status="DELETED",
                    verified_points=0,
                )

            self.vector_store.upsert_points(points)

            # 5. Verify ingestion via point retrieval
            retrieved = self.vector_store.retrieve_points(expected_ids)

            if len(retrieved) != len(expected_ids):
                raise RuntimeError(
                    f"Verification failed: expected {len(expected_ids)} points in Qdrant, "
                    f"retrieved {len(retrieved)}"
                )

            # 6. Update processing stage and video status upon successful verification
            stage.status = "COMPLETED"
            stage.completed_at = datetime.now(timezone.utc)
            stage.error_category = None
            stage.error_detail = None

            video.status = "INDEXED"
            session.flush()

            logger.info(
                "Indexed and verified points in Qdrant",
                extra={
                    "video_id": video.youtube_id,
                    "points_indexed": len(points),
                    "verified": len(retrieved),
                },
            )

            return IndexingResult(
                video_id=video.id,
                youtube_id=video.youtube_id,
                chunks_indexed=len(points),
                status="COMPLETED",
                verified_points=len(retrieved),
            )

        except Exception as exc:
            err_msg = str(exc)
            stage.status = "FAILED"
            stage.error_category = "INDEXING_FAILED"
            stage.error_detail = err_msg[:500]
            session.flush()

            logger.error(
                "Failed to index video into Qdrant",
                extra={"video_id": video.youtube_id, "error": err_msg[:200]},
            )
            return IndexingResult(
                video_id=video.id,
                youtube_id=video.youtube_id,
                chunks_indexed=0,
                status="FAILED",
                verified_points=0,
                error=err_msg,
            )

    def close(self) -> None:
        """Clean up embedding model memory."""
        self.embedding_service.close()
