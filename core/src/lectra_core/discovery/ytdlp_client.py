"""yt-dlp metadata provider.

Wraps yt-dlp so discovery logic can be tested with a fake provider.
No video, audio, or subtitle downloads ever happen here: every request
runs with ``download=False`` and ``skip_download``-style options.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol

from lectra_core.logging import get_logger

logger = get_logger("lectra.discovery.ytdlp")

# yt-dlp option defaults. ``extract_flat="in_playlist"`` means playlist entries
# are resolved without extracting each video's full information immediately.
BASE_YT_DLP_OPTIONS: Dict = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "skip_download": True,  # hard requirement: never download anything
    "extract_flat": "in_playlist",
    # Retry/timeouts handled explicitly by the caller, not silently ignored.
    "retries": 3,
    "socket_timeout": 30,
    "ignoreerrors": True,
    "extractor_retries": 2,
}

_ERROR_CATEGORY_MARKERS = [
    ("private video", "PRIVATE"),
    ("this video is private", "PRIVATE"),
    ("members-only", "MEMBERS_ONLY"),
    ("sign in to confirm", "AGE_OR_AUTH_REQUIRED"),
    ("age-restricted", "AGE_OR_AUTH_REQUIRED"),
    ("confirm your age", "AGE_OR_AUTH_REQUIRED"),
    ("removed by the uploader", "REMOVED"),
    ("does not exist", "REMOVED"),
    ("has been removed", "REMOVED"),
    ("copyright", "COPYRIGHT_RESTRICTED"),
    ("geo-restricted", "GEO_RESTRICTED"),
    ("not available in your country", "GEO_RESTRICTED"),
    ("unable to download", "DOWNLOAD_ERROR"),
    ("video unavailable", "UNAVAILABLE"),
    ("video is unavailable", "UNAVAILABLE"),
    ("sign in to", "AGE_OR_AUTH_REQUIRED"),
]


class MetadataProviderError(RuntimeError):
    """Raised when playlist-level metadata extraction fails entirely."""


class VideoMetadataError(RuntimeError):
    """Raised when a single video's metadata cannot be retrieved."""

    def __init__(self, youtube_id: str, message: str):
        self.youtube_id = youtube_id
        super().__init__(message)


def classify_error_message(message: str) -> str:
    """Map a yt-dlp error message to a stable error category."""
    lowered = (message or "").lower()
    for marker, category in _ERROR_CATEGORY_MARKERS:
        if marker in lowered:
            return category
    return "UNKNOWN_ERROR"


@dataclass(frozen=True)
class PlaylistEntry:
    """One entry from a playlist's flat listing."""

    youtube_id: str
    title: str
    url: str
    duration_seconds: Optional[float]
    position: int  # 0-based position as returned by yt-dlp


@dataclass(frozen=True)
class PlaylistInfo:
    """Playlist-level metadata from stage A discovery."""

    youtube_id: str
    title: str
    channel_name: Optional[str]
    entries: List[PlaylistEntry]


@dataclass(frozen=True)
class VideoInfo:
    """Per-video availability and metadata, when the video is accessible."""

    youtube_id: str
    title: str
    url: str
    duration_seconds: Optional[float]
    availability: str


class MetadataProvider(Protocol):
    """Interface for playlist/video metadata providers."""

    def get_playlist(self, url: str) -> PlaylistInfo: ...

    def get_video(self, video_url: str) -> VideoInfo: ...


class YtDlpProvider:
    """yt-dlp-backed implementation of MetadataProvider."""

    def __init__(self, options: Optional[Dict] = None):
        self._options = {**BASE_YT_DLP_OPTIONS, **(options or {})}

    # --- helpers -----------------------------------------------------

    def _extract_info(self, url: str, extra_options: Optional[Dict] = None):
        import yt_dlp  # type: ignore[import-untyped]  # imported lazily so unit tests can install fakes

        opts = {**self._options, **(extra_options or {})}
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    # --- provider interface -------------------------------------------

    def get_playlist(self, url: str) -> PlaylistInfo:
        """Extract flat playlist metadata.
        Malformed or invisible playlists raise MetadataProviderError.
        """
        try:
            raw = self._extract_info(url)
        except Exception as exc:  # yt-dlp DownloadError and friends
            raise MetadataProviderError(str(exc)) from exc

        if raw is None:
            raise MetadataProviderError(f"yt-dlp returned no information for playlist {url!r}.")

        entries: List[PlaylistEntry] = []
        position = 0
        for raw_entry in raw.get("entries") or []:
            if raw_entry is None:
                # yt-dlp could not even identify this entry; count and continue.
                logger.warning(
                    "Skipping an unidentifiable playlist entry (extractor returned None)."
                )
                continue
            youtube_id = raw_entry.get("id")
            if not youtube_id:
                logger.warning("Skipping playlist entry without a stable video ID.")
                continue
            entries.append(
                PlaylistEntry(
                    youtube_id=str(youtube_id),
                    title=str(raw_entry.get("title") or "Unknown title"),
                    url=_canonical_video_url(str(youtube_id)),
                    duration_seconds=_optional_float(raw_entry.get("duration")),
                    position=position,
                )
            )
            position += 1

        return PlaylistInfo(
            youtube_id=str(raw.get("id") or ""),
            title=str(raw.get("title") or "Unknown playlist"),
            channel_name=_channel_name(raw),
            entries=entries,
        )

    def get_video(self, video_url: str) -> VideoInfo:
        """Extract per-video metadata; raises VideoMetadataError when inaccessible."""
        try:
            raw = self._extract_info(video_url, extra_options={"extract_flat": True})
        except Exception as exc:
            raise VideoMetadataError(video_url, str(exc)) from exc
        if raw is None:
            raise VideoMetadataError(video_url, "yt-dlp returned no information for this video.")

        youtube_id = str(raw.get("id") or "")
        if not youtube_id:
            raise VideoMetadataError(video_url, "yt-dlp returned no video ID for this video.")

        title = str(raw.get("title") or "Unknown title")
        availability = str(raw.get("availability") or "public")
        if title in ("[Private video]", "[Deleted video]") or availability == "private":
            raise VideoMetadataError(video_url, f"Video is unavailable: {title}")

        return VideoInfo(
            youtube_id=youtube_id,
            title=title,
            url=_canonical_video_url(youtube_id),
            duration_seconds=_optional_float(raw.get("duration")),
            availability=availability,
        )


def _channel_name(raw: dict) -> Optional[str]:
    for key in ("channel", "uploader", "uploader_id", "playlist_uploader"):
        value = raw.get(key)
        if value:
            return str(value)
    return None


def _canonical_video_url(youtube_id: str) -> str:
    return f"https://www.youtube.com/watch?v={youtube_id}"


def _optional_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
