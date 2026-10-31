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
    """Service for generating, validating, and persisting 75-second video chunks."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        target_duration: float = 75.0,
        min_duration: float = 60.0,
        max_duration: float = 90.0,
    ):
        self.settings = settings or get_settings()
        self.target_duration = target_duration
        self.min_duration = min_duration
        self.max_duration = max_duration

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
        """Generate and persist 75-second chunks for a single video idempotently."""
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
        # For whisper or manual captions, deduplicator preserves text as is
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

        # 2. Accumulate into 75-second chunks with sentence-boundary preference
        chunks_data: List[ChunkData] = []
        chunk_idx = 0
        curr_start_idx = 0
        total_items = len(cleaned_pairs)

        while curr_start_idx < total_items:
            start_seg, _ = cleaned_pairs[curr_start_idx]
            start_time = float(start_seg.start_seconds)
            total_remaining = float(cleaned_pairs[-1][0].end_seconds) - start_time

            # If all remaining speech fits within max_duration, emit as final chunk
            if total_remaining <= self.max_duration:
                end_idx = total_items - 1
            else:
                end_idx = curr_start_idx
                for j in range(curr_start_idx, total_items):
                    seg, txt = cleaned_pairs[j]
                    curr_end = float(seg.end_seconds)
                    dur = curr_end - start_time
                    end_idx = j

                    ends_with_sentence = bool(_SENTENCE_END_RE.search(txt))

                    # Prefer sentence boundary when within min_duration and max_duration
                    if dur >= self.min_duration and ends_with_sentence:
                        break

                    # If next segment exceeds max_duration, stop here
                    if j + 1 < total_items:
                        next_end = float(cleaned_pairs[j + 1][0].end_seconds)
                        if (next_end - start_time) > self.max_duration:
                            break
                    elif dur >= self.target_duration:
                        break

            c_pairs = cleaned_pairs[curr_start_idx : end_idx + 1]
            chunk_text = " ".join(txt for _, txt in c_pairs)
            c_start = float(c_pairs[0][0].start_seconds)
            c_end = float(c_pairs[-1][0].end_seconds)
            c_dur = round(c_end - c_start, 3)

            # Deterministic UUID5 based on video ID and chunk index
            chunk_id = str(uuid.uuid5(CHUNK_UUID_NAMESPACE, f"{video.id}:{chunk_idx}"))
            token_count = count_tokens(chunk_text)

            chunks_data.append(
                ChunkData(
                    id=chunk_id,
                    video_id=video.id,
                    chunk_index=chunk_idx,
                    start_seconds=round(c_start, 3),
                    end_seconds=round(c_end, 3),
                    duration_seconds=c_dur,
                    text=chunk_text,
                    token_count=token_count,
                    source_segment_start_index=int(c_pairs[0][0].segment_index),
                    source_segment_end_index=int(c_pairs[-1][0].segment_index),
                )
            )

            chunk_idx += 1
            curr_start_idx = end_idx + 1

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
