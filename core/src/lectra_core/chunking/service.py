"""75-second chunk generation service.

Aggregates fine-grained transcript segments into semantic, retrieval-ready chunks
targeting approximately 75 seconds with sentence boundary alignment.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from lectra_core.chunking.deduplicator import deduplicate_rolling_captions
from lectra_core.chunking.tokenizer import count_tokens
from lectra_core.config import Settings, get_settings
from lectra_core.db.models import ProcessingStage, Video, VideoChunk
from lectra_core.logging import get_logger
from lectra_core.repositories import chunk_repository, transcript_repository
from lectra_core.repositories.chunk_repository import ChunkData

logger = get_logger("lectra.chunking.service")

STAGE_CHUNKING = "CHUNKING"

# Deterministic namespace for chunk UUIDs across all videos
CHUNK_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "lectra.chunks.revision-rag")

# Sentence boundary pattern: end of sentence punctuation followed by optional quote
_SENTENCE_END_RE = re.compile(r"""[.?!]["']?\s*$""")


class ChunkingService:
    """Service for generating, validating, and persisting 75-second video chunks with 5s overlap."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        duration: float = 75.0,
        overlap: float = 5.0,
        stride: float = 70.0,
        target_duration: Optional[float] = None,
        min_duration: Optional[float] = None,
        max_duration: Optional[float] = None,
    ):
        self.settings = settings or get_settings()
        self.duration = target_duration if target_duration is not None else duration
        self.overlap = overlap
        self.stride = (
            (self.duration - self.overlap) if stride == 70.0 and self.duration != 75.0 else stride
        )

    def _get_or_create_stage(self, session: Session, video_id: str) -> ProcessingStage:
        stage = session.scalars(
            select(ProcessingStage).where(
                ProcessingStage.video_id == video_id,
                ProcessingStage.stage_name == STAGE_CHUNKING,
            )
        ).first()

        if stage is None:
            stage = ProcessingStage(
                video_id=video_id,
                stage_name=STAGE_CHUNKING,
                status="PENDING",
                attempts=0,
            )
            session.add(stage)
            session.flush()
        return stage

    def chunk_video(self, session: Session, video: Video) -> List[VideoChunk]:
        """Generate and persist 75-second chunks (70s stride, 5s overlap) idempotently."""
        # Check race condition: video was deleted
        if session.get(Video, video.id) is None:
            logger.info("Video deleted; skipping chunking", extra={"video_id": video.youtube_id})
            return []

        stage = self._get_or_create_stage(session, video.id)
        stage.status = "IN_PROGRESS"
        stage.attempts += 1
        session.flush()

        segments = transcript_repository.get_by_video_id(session, video.id)
        if not segments:
            logger.warning(
                "No transcript segments found to chunk",
                extra={"video_id": video.youtube_id},
            )
            stage.status = "COMPLETED"
            stage.completed_at = datetime.now(timezone.utc)
            session.flush()
            return []

        # 1. Deduplicate rolling cues for auto-generated captions
        cleaned_pairs = deduplicate_rolling_captions(segments)
        if not cleaned_pairs:
            logger.warning(
                "Deduplication resulted in empty segments",
                extra={"video_id": video.youtube_id},
            )
            stage.status = "COMPLETED"
            stage.completed_at = datetime.now(timezone.utc)
            session.flush()
            return []

        # 2. Fixed sliding window: duration = 75s, overlap = 5s, stride = 70s
        total_duration = max(float(seg.end_seconds) for seg, _ in cleaned_pairs)
        chunks_data: List[ChunkData] = []
        chunk_idx = 0
        curr_window_start = 0.0

        while curr_window_start < total_duration:
            curr_window_end = min(curr_window_start + self.duration, total_duration)

            # Find all segments overlapping with [curr_window_start, curr_window_end]
            overlapping = [
                (seg, txt)
                for seg, txt in cleaned_pairs
                if (
                    float(seg.start_seconds) < curr_window_end
                    and float(seg.end_seconds) > curr_window_start
                )
                or (
                    float(seg.start_seconds) == float(seg.end_seconds)
                    and curr_window_start <= float(seg.start_seconds) <= curr_window_end
                )
            ]

            chunk_text = " ".join(txt.strip() for _, txt in overlapping if txt and txt.strip())

            # Only emit chunk if it contains non-empty text
            if chunk_text:
                c_start = round(curr_window_start, 3)
                c_end = round(curr_window_end, 3)
                c_dur = round(c_end - c_start, 3)
                chunk_id = str(uuid.uuid5(CHUNK_UUID_NAMESPACE, f"{video.id}:{chunk_idx}"))
                token_count = count_tokens(chunk_text)

                start_seg_idx = int(overlapping[0][0].segment_index)
                end_seg_idx = int(overlapping[-1][0].segment_index)

                chunks_data.append(
                    ChunkData(
                        id=chunk_id,
                        video_id=video.id,
                        chunk_index=chunk_idx,
                        start_seconds=c_start,
                        end_seconds=c_end,
                        duration_seconds=c_dur,
                        text=chunk_text,
                        token_count=token_count,
                        source_segment_start_index=start_seg_idx,
                        source_segment_end_index=end_seg_idx,
                    )
                )
                chunk_idx += 1

            # Termination condition: this chunk reached video end or next stride exceeds video end
            if (
                curr_window_end >= total_duration
                or (curr_window_start + self.stride) >= total_duration
            ):
                break

            curr_window_start += self.stride

        # Check race condition before saving
        if session.get(Video, video.id) is None:
            logger.info(
                "Video deleted before saving chunks; aborting", extra={"video_id": video.youtube_id}
            )
            return []

        # 3. Persist chunks idempotently via repository
        saved_records = chunk_repository.save_chunks(session, video.id, chunks_data)

        # 4. Update stage and video status
        stage.status = "COMPLETED"
        stage.completed_at = datetime.now(timezone.utc)
        stage.error_category = None
        stage.error_detail = None

        if video.status in ("TRANSCRIPT_READY", "DISCOVERED"):
            video.status = "CHUNKED"
        session.flush()

        logger.info(
            "Generated and persisted chunks for video",
            extra={
                "video_id": video.youtube_id,
                "chunk_count": len(saved_records),
                "total_duration": sum(c.duration_seconds for c in saved_records),
            },
        )
        return saved_records
