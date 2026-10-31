"""Stage A playlist discovery service.

Runs yt-dlp-backed playlist discovery, reconciles results with existing
SQLite records (idempotent on re-submission), and records every video that
cannot be processed as an explicit exception rather than terminating the job.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from lectra_core.config import Settings
from lectra_core.db.models import Playlist, Video
from lectra_core.db.session import get_session_factory
from lectra_core.discovery.url_validation import PlaylistUrl, validate_playlist_url
from lectra_core.discovery.ytdlp_client import (
    MetadataProvider,
    VideoMetadataError,
    YtDlpProvider,
    classify_error_message,
)
from lectra_core.logging import get_logger
from lectra_core.repositories import playlist_repository, video_repository

logger = get_logger("lectra.discovery.service")


@dataclass
class DiscoveryResult:
    """Summary counts of one discovery run for a playlist."""

    playlist_db_id: str
    youtube_id: str
    title: str
    normalized_url: str
    entries_seen: int = 0
    distinct_videos: int = 0
    discovered: int = 0
    unavailable: int = 0
    duplicate_entries: int = 0
    invalid_entries: int = 0
    unavailable_ids: List[str] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)


class DiscoveryError(RuntimeError):
    """Raised when discovery cannot proceed at playlist level."""


class DiscoveryService:
    """Discovers a playlist manifest and persists it durably in SQLite."""

    def __init__(self, provider: Optional[MetadataProvider] = None):
        self._provider: MetadataProvider = provider or YtDlpProvider()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def discover_by_url(self, url: str, settings: Optional[Settings] = None) -> DiscoveryResult:
        """Discover a playlist by URL and persist its manifest (sync facade for tests/CLI)."""
        factory = get_session_factory(settings)
        session = factory()
        try:
            return self.discover(session, url)
        finally:
            session.close()

    def discover(self, session: Session, url: str) -> DiscoveryResult:
        """Run discovery inside the given session."""
        playlist_url = validate_playlist_url(url)
        try:
            return self._discover_raw(session, playlist_url)
        except Exception as exc:
            self._mark_playlist_failed(session, playlist_url, exc)
            raise

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _discover_raw(self, session: Session, playlist_url: PlaylistUrl) -> DiscoveryResult:
        try:
            playlist_info = self._provider.get_playlist(playlist_url.normalized_url)
        except Exception as exc:
            raise DiscoveryError(str(exc)) from exc

        playlist = self._upsert_playlist(
            session,
            playlist_url,
            title=playlist_info.title,
            channel_name=playlist_info.channel_name,
            declared_count=len(playlist_info.entries),
            status="DISCOVERY_RUNNING",
            discovery_error=None,
        )
        session.commit()  # playlist row visible before per-video work starts

        result = DiscoveryResult(
            playlist_db_id=playlist.id,
            youtube_id=playlist_url.youtube_id,
            title=playlist_info.title,
            normalized_url=playlist_url.normalized_url,
        )

        seen_ids: Dict[str, int] = {}
        for entry in playlist_info.entries:
            result.entries_seen += 1

            duplicate_of_position = seen_ids.get(entry.youtube_id)
            if duplicate_of_position is not None:
                result.duplicate_entries += 1
                logger.warning(
                    "Duplicate playlist entry found; keeping first occurrence",
                    extra={
                        "playlist_id": playlist_url.youtube_id,
                        "video_id": entry.youtube_id,
                        "first_position": duplicate_of_position,
                        "repeated_position": entry.position,
                    },
                )
                continue
            seen_ids[entry.youtube_id] = entry.position

            video = self._reconcile_entry(session, playlist, entry, result)
            if video is None:
                continue
            result.distinct_videos += 1
            session.commit()  # durable manifest survives restart after each entry

            logger.info(
                "Video reconciled",
                extra={
                    "playlist_id": playlist_url.youtube_id,
                    "video_id": entry.youtube_id,
                    "position": entry.position,
                    "status": video.status,
                    "availability": video.availability,
                },
            )

        playlist.status = "DISCOVERY_COMPLETED"
        playlist.video_count = len(playlist_info.entries)
        playlist.discovery_error = None
        session.commit()

        logger.info(
            "Playlist discovery completed",
            extra={
                "playlist_id": playlist_url.youtube_id,
                "playlist": playlist_url.youtube_id,
                "entries_seen": result.entries_seen,
                "distinct_videos": result.distinct_videos,
                "discovered": result.discovered,
                "unavailable": result.unavailable,
                "duplicate_entries": result.duplicate_entries,
                "invalid_entries": result.invalid_entries,
            },
        )
        return result

    def _reconcile_entry(
        self, session: Session, playlist: Playlist, entry, result: DiscoveryResult
    ) -> Optional[Video]:
        """Reconcile one playlist entry, recording unavailable videos as exceptions."""
        existing = video_repository.get(playlist.id, entry.youtube_id, session)

        # Guard: never wipe downstream progress with discovery-only data.
        if existing is not None and video_repository.is_downstream_in_progress(existing):
            self._refresh_processed_metadata(existing, entry)
            logger.info(
                "Video already progressed past discovery; discovery fields not clobbered",
                extra={"video_id": entry.youtube_id, "status": existing.status},
            )
            return existing

        try:
            probed = self._provider.get_video(entry.url)
        except VideoMetadataError as exc:
            return self._record_unavailable_video(
                session,
                playlist,
                entry,
                result,
                error_category=classify_error_message(str(exc)),
                message=str(exc),
            )

        if existing is None:
            existing = Video(
                playlist_id=playlist.id,
                youtube_id=entry.youtube_id,
                title=probed.title,
                url=probed.url,
                duration_seconds=probed.duration_seconds,
                position=entry.position,
                status="DISCOVERED",
                availability=probed.availability,
                discovery_error=None,
            )
            session.add(existing)
            result.discovered += 1
        else:
            video_repository.apply_discovery(
                session,
                existing,
                title=probed.title,
                url=probed.url,
                duration_seconds=probed.duration_seconds,
                position=entry.position,
                status="DISCOVERED",
                availability=probed.availability,
                discovery_error=None,
            )
        return existing

    def _record_unavailable_video(
        self, session, playlist, entry, result, error_category: str, message: str
    ) -> Video:
        """Persist an explicit exception record; never raise for a single video."""
        sanitized = (message or "").strip()[:500]
        existing = video_repository.get(playlist.id, entry.youtube_id, session)
        if existing is None:
            video = Video(
                playlist_id=playlist.id,
                youtube_id=entry.youtube_id,
                title=entry.title,
                url=entry.url,
                duration_seconds=entry.duration_seconds,
                position=entry.position,
                status="SKIPPED_UNAVAILABLE",
                availability=error_category,
                discovery_error=sanitized,
            )
            session.add(video)
        else:
            video = existing
            video_repository.apply_discovery(
                session,
                video,
                title=existing.title,
                position=entry.position,
                status="SKIPPED_UNAVAILABLE",
                availability=error_category,
                discovery_error=sanitized,
            )
        result.unavailable += 1
        result.unavailable_ids.append(entry.youtube_id)
        result.errors.append(
            {"video_id": entry.youtube_id, "category": error_category, "detail": sanitized}
        )
        logger.warning(
            "Video recorded as unavailable",
            extra={"video_id": entry.youtube_id, "category": error_category},
        )
        return video

    def _refresh_processed_metadata(self, video: Video, entry) -> None:
        """Update timestamps-sensitive metadata only, never on stage status."""
        video.duration_seconds = video.duration_seconds or entry.duration_seconds

    def _upsert_playlist(
        self, session, playlist_url, *, title, channel_name, declared_count, status, discovery_error
    ) -> Playlist:
        playlist = playlist_repository.get_by_youtube_id(session, playlist_url.youtube_id)
        if playlist is None:
            playlist = Playlist(
                youtube_id=playlist_url.youtube_id,
                url=playlist_url.normalized_url,
                title=title,
                channel_name=channel_name,
                video_count=declared_count,
                status=status,
                discovery_error=discovery_error,
            )
            session.add(playlist)
        else:
            # A previously completed manifest keeps its video_count until this run finishes.
            playlist.url = playlist_url.normalized_url
            playlist.title = title
            playlist.channel_name = channel_name or playlist.channel_name
            playlist.status = status
            playlist.discovery_error = discovery_error
        session.flush()
        return playlist

    def _mark_playlist_failed(
        self, session: Session, playlist_url: PlaylistUrl, exc: Exception
    ) -> None:
        playlist = playlist_repository.get_by_youtube_id(session, playlist_url.youtube_id)
        err_msg = (str(exc) or "Discovery failed")[:500]
        if playlist is None:
            playlist = Playlist(
                youtube_id=playlist_url.youtube_id,
                url=playlist_url.normalized_url,
                title="Unknown playlist",
                channel_name=None,
                video_count=0,
                status="DISCOVERY_FAILED",
                discovery_error=err_msg,
            )
            session.add(playlist)
        else:
            playlist.status = "DISCOVERY_FAILED"
            playlist.discovery_error = err_msg
        session.commit()
        logger.error(
            "Playlist discovery failed",
            extra={"playlist": playlist_url.youtube_id, "error": err_msg[:200]},
        )
