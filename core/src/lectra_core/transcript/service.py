"""Transcript acquisition and persistence service.

Orchestrates subtitle extraction, normalization, database persistence,
local artifact storage, and video/stage status transitions.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from lectra_core.config import Settings, get_settings
from lectra_core.db.models import ProcessingStage, Video
from lectra_core.logging import get_logger
from lectra_core.repositories import transcript_repository
from lectra_core.transcript.formats import parse_subtitle_content
from lectra_core.transcript.models import (
    AudioDownloadError,
    CaptionsUnavailableError,
    MalformedSubtitleDataError,
    NonEnglishAudioError,
    TranscriptError,
    TranscriptExtractionError,
    TranscriptExtractionResult,
    VideoUnavailableError,
    WhisperTranscriptionError,
)
from lectra_core.transcript.whisper_transcriber import (
    FasterWhisperTranscriber,
    WhisperTranscriberProtocol,
)
from lectra_core.transcript.ytdlp_extractor import SubtitleExtractor, YtDlpSubtitleExtractor

logger = get_logger("lectra.transcript.service")

STAGE_TRANSCRIPT_ACQUISITION = "TRANSCRIPT_ACQUISITION"


@dataclass
class VideoTranscriptSummary:
    """Result summary for an individual video."""

    video_id: str
    youtube_id: str
    status: str  # TRANSCRIPT_READY, NEEDS_TRANSCRIPTION, etc.
    language: Optional[str] = None
    source: Optional[str] = None
    segment_count: int = 0
    artifact_path: Optional[str] = None
    error_category: Optional[str] = None
    error_detail: Optional[str] = None


@dataclass
class PlaylistTranscriptResult:
    """Aggregated results of transcript extraction for a playlist."""

    playlist_id: str
    total_eligible: int = 0
    transcripts_ready: int = 0
    needs_transcription: int = 0
    skipped_unavailable: int = 0
    failed: int = 0
    already_done: int = 0
    video_summaries: List[VideoTranscriptSummary] = field(default_factory=list)


class TranscriptService:
    """Service responsible for extracting, validating, and persisting transcripts."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        extractor: Optional[SubtitleExtractor] = None,
        transcriber: Optional[WhisperTranscriberProtocol] = None,
    ):
        self.settings = settings or get_settings()
        self.extractor: SubtitleExtractor = extractor or YtDlpSubtitleExtractor(self.settings)
        self.transcriber: WhisperTranscriberProtocol = transcriber or FasterWhisperTranscriber(
            self.settings
        )

    def extract_for_playlist(self, session: Session, playlist_id: str) -> PlaylistTranscriptResult:
        """Extract transcripts for all eligible videos in a playlist."""
        eligible_videos = session.scalars(
            select(Video)
            .where(
                Video.playlist_id == playlist_id,
                Video.status.in_(["DISCOVERED", "EXTRACTION_FAILED", "NEEDS_TRANSCRIPTION"]),
            )
            .order_by(Video.position.asc())
        ).all()

        result = PlaylistTranscriptResult(
            playlist_id=playlist_id,
            total_eligible=len(eligible_videos),
        )

        for video in eligible_videos:
            summary = self.process_video(session, video)
            result.video_summaries.append(summary)

            if summary.status == "TRANSCRIPT_READY":
                result.transcripts_ready += 1
            elif summary.status == "NEEDS_TRANSCRIPTION":
                result.needs_transcription += 1
            elif summary.status == "SKIPPED_UNAVAILABLE":
                result.skipped_unavailable += 1
            elif summary.status == "ALREADY_DONE":
                result.already_done += 1
            else:
                result.failed += 1

            # Commit after each video so progress is durable and survives interruptions
            session.commit()

        logger.info(
            "Playlist transcript extraction completed",
            extra={
                "playlist_id": playlist_id,
                "total": result.total_eligible,
                "transcripts_ready": result.transcripts_ready,
                "needs_transcription": result.needs_transcription,
                "unavailable": result.skipped_unavailable,
                "failed": result.failed,
            },
        )
        return result

    def process_video(self, session: Session, video: Video) -> VideoTranscriptSummary:
        """Process transcript acquisition for a single video idempotently."""
        # Check idempotency: If already transcript-ready, do not reprocess
        if video.status == "TRANSCRIPT_READY" and transcript_repository.has_transcripts(
            session, video.id
        ):
            logger.info(
                "Video already has transcripts; skipping", extra={"video_id": video.youtube_id}
            )
            return VideoTranscriptSummary(
                video_id=video.id,
                youtube_id=video.youtube_id,
                status="ALREADY_DONE",
            )

        if video.status == "SKIPPED_UNAVAILABLE":
            logger.info(
                "Video is marked unavailable; skipping", extra={"video_id": video.youtube_id}
            )
            return VideoTranscriptSummary(
                video_id=video.id,
                youtube_id=video.youtube_id,
                status="SKIPPED_UNAVAILABLE",
                error_category=video.availability or "UNAVAILABLE",
                error_detail=video.discovery_error,
            )

        stage = self._get_or_create_stage(session, video.id)
        stage.status = "IN_PROGRESS"
        stage.attempts += 1
        session.flush()

        # If video is already marked NEEDS_TRANSCRIPTION, jump directly to Whisper
        if video.status == "NEEDS_TRANSCRIPTION":
            return self._run_whisper_fallback(session, video, stage)

        try:
            # 1. Extract raw track via provider
            raw_track = self.extractor.extract_subtitles(video.url)

            # 2. Parse into normalized segment models
            segments = parse_subtitle_content(
                content=raw_track.content,
                format_name=raw_track.format_name,
                language=raw_track.language,
                source=raw_track.source,
            )

            if not segments:
                # Subtitle track was provided but had no non-empty segments
                raise CaptionsUnavailableError("Subtitle track contained no valid text segments.")

            extraction_result = TranscriptExtractionResult(
                youtube_id=video.youtube_id,
                language=raw_track.language,
                source=raw_track.source,
                segments=segments,
            )

            # 3. Persist local artifact atomically before database commit
            artifact_path = self._write_artifact(video, extraction_result)

            # 4. Persist segments in SQLite via repository
            transcript_repository.save_segments(session, video.id, segments)

            # 5. Mark stage COMPLETED and video TRANSCRIPT_READY
            stage.status = "COMPLETED"
            stage.artifact_path = str(artifact_path)
            stage.error_category = None
            stage.error_detail = None
            stage.completed_at = datetime.now(timezone.utc)

            video.status = "TRANSCRIPT_READY"
            video.discovery_error = None
            session.flush()

            logger.info(
                "Transcript extracted and persisted successfully",
                extra={
                    "video_id": video.youtube_id,
                    "language": raw_track.language,
                    "source": raw_track.source,
                    "segment_count": len(segments),
                    "artifact_path": str(artifact_path),
                },
            )

            return VideoTranscriptSummary(
                video_id=video.id,
                youtube_id=video.youtube_id,
                status="TRANSCRIPT_READY",
                language=raw_track.language,
                source=raw_track.source,
                segment_count=len(segments),
                artifact_path=str(artifact_path),
            )

        except CaptionsUnavailableError as exc:
            # Video is accessible but has no usable English captions; invoke local Whisper fallback
            logger.info(
                "Captions unavailable; falling back to local Whisper transcription",
                extra={"video_id": video.youtube_id, "reason": str(exc)},
            )
            return self._run_whisper_fallback(session, video, stage)

        except VideoUnavailableError as exc:
            # Video is private, deleted, removed, or region-restricted
            stage.status = "FAILED"
            stage.error_category = "UNAVAILABLE"
            stage.error_detail = exc.reason[:500]
            stage.completed_at = datetime.now(timezone.utc)

            video.status = "SKIPPED_UNAVAILABLE"
            video.availability = "UNAVAILABLE"
            video.discovery_error = exc.reason[:500]
            session.flush()

            logger.warning(
                "Video unavailable during transcript extraction",
                extra={"video_id": video.youtube_id, "reason": exc.reason},
            )
            return VideoTranscriptSummary(
                video_id=video.id,
                youtube_id=video.youtube_id,
                status="SKIPPED_UNAVAILABLE",
                error_category="UNAVAILABLE",
                error_detail=exc.reason,
            )

        except (
            TranscriptExtractionError,
            MalformedSubtitleDataError,
            TranscriptError,
            Exception,
        ) as exc:
            err_msg = str(exc)
            category = (
                "EXTRACTION_FAILED"
                if not isinstance(exc, MalformedSubtitleDataError)
                else "MALFORMED_SUBTITLES"
            )
            stage.status = "FAILED"
            stage.error_category = category
            stage.error_detail = err_msg[:500]

            video.status = "EXTRACTION_FAILED"
            video.discovery_error = err_msg[:500]
            session.flush()

            logger.error(
                "Failed to extract transcript for video",
                extra={"video_id": video.youtube_id, "error": err_msg[:200]},
            )
            return VideoTranscriptSummary(
                video_id=video.id,
                youtube_id=video.youtube_id,
                status="EXTRACTION_FAILED",
                error_category=category,
                error_detail=err_msg,
            )

    def _run_whisper_fallback(
        self, session: Session, video: Video, stage: ProcessingStage
    ) -> VideoTranscriptSummary:
        """Execute local Whisper transcription fallback for a video lacking captions."""
        try:
            whisper_result = self.transcriber.transcribe_video(video.url, video.youtube_id)

            # Persist local artifact atomically before database commit
            artifact_path = self._write_artifact(video, whisper_result)

            # Persist segments in SQLite via repository
            transcript_repository.save_segments(session, video.id, whisper_result.segments)

            # Mark stage COMPLETED and video TRANSCRIPT_READY
            stage.status = "COMPLETED"
            stage.artifact_path = str(artifact_path)
            stage.error_category = None
            stage.error_detail = None
            stage.completed_at = datetime.now(timezone.utc)

            video.status = "TRANSCRIPT_READY"
            video.discovery_error = None
            session.flush()

            logger.info(
                "Whisper transcript persisted successfully",
                extra={
                    "video_id": video.youtube_id,
                    "language": whisper_result.language,
                    "source": whisper_result.source,
                    "segment_count": len(whisper_result.segments),
                    "artifact_path": str(artifact_path),
                },
            )

            return VideoTranscriptSummary(
                video_id=video.id,
                youtube_id=video.youtube_id,
                status="TRANSCRIPT_READY",
                language=whisper_result.language,
                source=whisper_result.source,
                segment_count=len(whisper_result.segments),
                artifact_path=str(artifact_path),
            )

        except NonEnglishAudioError as non_en_exc:
            # Non-English audio detected; strictly enforce English-only policy (no translation)
            stage.status = "SKIPPED"
            stage.error_category = "NON_ENGLISH_AUDIO"
            stage.error_detail = str(non_en_exc)[:500]
            stage.completed_at = datetime.now(timezone.utc)

            video.status = "NEEDS_TRANSCRIPTION"
            video.discovery_error = str(non_en_exc)[:500]
            session.flush()

            logger.warning(
                "Video contains non-English audio; marked NEEDS_TRANSCRIPTION",
                extra={
                    "video_id": video.youtube_id,
                    "detected_language": non_en_exc.detected_language,
                },
            )
            return VideoTranscriptSummary(
                video_id=video.id,
                youtube_id=video.youtube_id,
                status="NEEDS_TRANSCRIPTION",
                error_category="NON_ENGLISH_AUDIO",
                error_detail=str(non_en_exc),
            )

        except VideoUnavailableError as unavail_exc:
            stage.status = "FAILED"
            stage.error_category = "UNAVAILABLE"
            stage.error_detail = unavail_exc.reason[:500]
            stage.completed_at = datetime.now(timezone.utc)

            video.status = "SKIPPED_UNAVAILABLE"
            video.availability = "UNAVAILABLE"
            video.discovery_error = unavail_exc.reason[:500]
            session.flush()

            logger.warning(
                "Video unavailable during Whisper transcription",
                extra={"video_id": video.youtube_id, "reason": unavail_exc.reason},
            )
            return VideoTranscriptSummary(
                video_id=video.id,
                youtube_id=video.youtube_id,
                status="SKIPPED_UNAVAILABLE",
                error_category="UNAVAILABLE",
                error_detail=unavail_exc.reason,
            )

        except (
            AudioDownloadError,
            WhisperTranscriptionError,
            Exception,
        ) as whisper_err:
            err_msg = str(whisper_err)
            category = (
                "RATE_LIMITED"
                if isinstance(whisper_err, AudioDownloadError) and whisper_err.is_rate_limited
                else "WHISPER_FAILED"
            )
            stage.status = "FAILED"
            stage.error_category = category
            stage.error_detail = err_msg[:500]

            video.status = "EXTRACTION_FAILED"
            video.discovery_error = err_msg[:500]
            session.flush()

            logger.error(
                "Whisper transcription failed for video",
                extra={"video_id": video.youtube_id, "error": err_msg[:200]},
            )
            return VideoTranscriptSummary(
                video_id=video.id,
                youtube_id=video.youtube_id,
                status="EXTRACTION_FAILED",
                error_category=category,
                error_detail=err_msg,
            )

    def _get_or_create_stage(self, session: Session, video_id: str) -> ProcessingStage:
        stage = session.scalars(
            select(ProcessingStage).where(
                ProcessingStage.video_id == video_id,
                ProcessingStage.stage_name == STAGE_TRANSCRIPT_ACQUISITION,
            )
        ).first()

        if stage is None:
            stage = ProcessingStage(
                video_id=video_id,
                stage_name=STAGE_TRANSCRIPT_ACQUISITION,
                status="PENDING",
                attempts=0,
            )
            session.add(stage)
            session.flush()
        return stage

    def _write_artifact(self, video: Video, result: TranscriptExtractionResult) -> Path:
        """Atomically persist transcript segments to local JSON artifact file."""
        transcripts_dir = self.settings.artifacts_dir / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)

        final_path = transcripts_dir / f"{video.youtube_id}_raw.json"
        temp_path = transcripts_dir / f"{video.youtube_id}_raw.json.tmp"

        payload = {
            "video_id": video.id,
            "youtube_id": video.youtube_id,
            "title": video.title,
            "language": result.language,
            "source": result.source,
            "segment_count": len(result.segments),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "segments": [
                {
                    "segment_index": seg.segment_index,
                    "start_seconds": seg.start_seconds,
                    "end_seconds": seg.end_seconds,
                    "duration_seconds": seg.duration_seconds,
                    "text": seg.text,
                    "language": seg.language,
                    "source": seg.source,
                }
                for seg in result.segments
            ],
        }

        # Write to temp file then atomic rename
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        os.replace(temp_path, final_path)
        return final_path
