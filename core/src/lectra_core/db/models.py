"""SQLAlchemy ORM models for job queue and metadata storage."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lectra_core.db.base import Base


class Job(Base):
    """Job record representing background tasks (discovery, ingestion, video retry)."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), default="QUEUED", nullable=False, index=True
    )  # QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)


class Playlist(Base):
    """Metadata record for an ingested YouTube playlist."""

    __tablename__ = "playlists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    youtube_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    channel_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    video_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # States: DISCOVERY_QUEUED, DISCOVERY_RUNNING, DISCOVERY_COMPLETED, DISCOVERY_FAILED
    status: Mapped[str] = mapped_column(
        String(50), default="DISCOVERY_QUEUED", nullable=False, index=True
    )
    discovery_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    videos: Mapped[List["Video"]] = relationship(
        "Video", back_populates="playlist", cascade="all, delete-orphan"
    )


class Video(Base):
    """Metadata record for a video discovered in a playlist."""

    __tablename__ = "videos"
    __table_args__ = (
        UniqueConstraint("playlist_id", "youtube_id", name="uq_videos_playlist_youtube_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    playlist_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    youtube_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # States: DISCOVERED, TRANSCRIPT_READY, ENGLISH_READY, CHUNKED, INDEXED,
    # SKIPPED_UNAVAILABLE, etc.
    status: Mapped[str] = mapped_column(
        String(50), default="DISCOVERED", nullable=False, index=True
    )
    # yt-dlp availability value when known ('public', 'unlisted', 'private', ...)
    # or a classified error category.
    availability: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Sanitized discovery-time failure detail. Never the whole traceback.
    discovery_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    playlist: Mapped["Playlist"] = relationship("Playlist", back_populates="videos")
    stages: Mapped[List["ProcessingStage"]] = relationship(
        "ProcessingStage", back_populates="video", cascade="all, delete-orphan"
    )
    transcripts: Mapped[List["TranscriptSegment"]] = relationship(
        "TranscriptSegment", back_populates="video", cascade="all, delete-orphan"
    )
    chunks: Mapped[List["VideoChunk"]] = relationship(
        "VideoChunk", back_populates="video", cascade="all, delete-orphan"
    )


class ProcessingStage(Base):
    """Per-stage checkpoint for a video's ingestion lifecycle."""

    __tablename__ = "processing_stages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="PENDING", nullable=False
    )  # PENDING, IN_PROGRESS, COMPLETED, FAILED
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    artifact_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    video: Mapped["Video"] = relationship("Video", back_populates="stages")


class TranscriptSegment(Base):
    """Timestamped segment of an original video transcript (Phase 3.1)."""

    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("video_id", "segment_index", name="uq_transcript_segments_video_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # "manual" | "generated"

    video: Mapped["Video"] = relationship("Video", back_populates="transcripts")


class VideoChunk(Base):
    """Derived 75-second retrieval chunk aggregated from transcript segments (Phase 4)."""

    __tablename__ = "video_chunks"
    __table_args__ = (
        UniqueConstraint("video_id", "chunk_index", name="uq_video_chunks_video_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_segment_start_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_segment_end_index: Mapped[int] = mapped_column(Integer, nullable=False)

    video: Mapped["Video"] = relationship("Video", back_populates="chunks")
