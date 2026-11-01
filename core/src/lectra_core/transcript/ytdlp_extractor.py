"""yt-dlp-based subtitle extractor.

Extracts subtitles without downloading video or audio streams.
Extracts English subtitles only (manual preferred over auto-generated).
If no English subtitles are available, raises CaptionsUnavailableError so the
caller can mark the video NEEDS_TRANSCRIPTION for a future Whisper fallback.
Prefers structured JSON3 format over other subtitle formats.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union

from lectra_core.config import Settings, get_settings
from lectra_core.discovery.ytdlp_client import classify_error_message
from lectra_core.logging import get_logger
from lectra_core.transcript.models import (
    CaptionsUnavailableError,
    MalformedSubtitleDataError,
    TranscriptExtractionError,
    VideoUnavailableError,
)

logger = get_logger("lectra.transcript.ytdlp")

_PREFERRED_FORMATS = ("json3", "vtt", "srv3", "srv2", "srv1", "ttml")


@dataclass(frozen=True)
class RawSubtitleTrack:
    """Raw subtitle payload and metadata extracted for a video."""

    content: Union[str, Dict[str, Any]]
    format_name: str
    language: str
    source: str  # "manual" | "generated"


class SubtitleExtractor(Protocol):
    """Protocol for subtitle extraction providers."""

    def extract_subtitles(self, video_url: str) -> RawSubtitleTrack: ...


def _is_translated_track(fmt_list: List[Dict[str, Any]]) -> bool:
    """Check if a track consists of auto-translated captions (e.g. tlang= in URL)."""
    for fmt in fmt_list:
        url = str(fmt.get("url") or "")
        if "tlang=" in url:
            return True
    return False


def select_best_track(
    subtitles: Dict[str, List[Dict[str, Any]]],
    automatic_captions: Dict[str, List[Dict[str, Any]]],
    preferred_languages: Optional[List[str]] = None,
    prefer_manual: bool = False,
    allow_non_english: bool = True,
) -> Optional[Tuple[List[Dict[str, Any]], str, str]]:
    """Select the best available subtitle track according to captions-first priority.

    Priority:
    1. English auto-generated captions (preferred primary source).
    2. English manual captions (if auto-generated is unavailable).
    3. Hindi manual caption tracks.
    4. Hindi auto-generated caption tracks.
    5. Other manual caption tracks.
    6. Other auto-generated caption tracks.

    Auto-translated tracks (containing `tlang=`) are skipped to respect pristine source
    transcripts and rely on local translation.

    Returns: (format_list, selected_language, source_type) or None if no usable captions exist.
    """
    manual_tracks = subtitles or {}
    auto_tracks = automatic_captions or {}

    def _is_en(code: str) -> bool:
        c = code.lower().strip()
        return c == "en" or c.startswith("en-") or c.startswith("en.")

    def _is_hi(code: str) -> bool:
        c = code.lower().strip()
        return c == "hi" or c.startswith("hi-") or c.startswith("hi.")

    # 1. Prefer English auto-generated captions as primary source
    for lang_code, fmt_list in auto_tracks.items():
        if _is_en(lang_code) and fmt_list and not _is_translated_track(fmt_list):
            return fmt_list, lang_code, "generated"

    # 2. English manual captions
    for lang_code, fmt_list in manual_tracks.items():
        if _is_en(lang_code) and fmt_list and not _is_translated_track(fmt_list):
            return fmt_list, lang_code, "manual"

    if allow_non_english:
        # 3. Hindi manual tracks
        for lang_code, fmt_list in manual_tracks.items():
            if _is_hi(lang_code) and fmt_list and not _is_translated_track(fmt_list):
                return fmt_list, lang_code, "manual"

        # 4. Hindi auto-generated tracks
        for lang_code, fmt_list in auto_tracks.items():
            if _is_hi(lang_code) and fmt_list and not _is_translated_track(fmt_list):
                return fmt_list, lang_code, "generated"

        # 5. Other manual tracks (non-English, non-Hindi)
        for lang_code, fmt_list in manual_tracks.items():
            if fmt_list and not _is_translated_track(fmt_list):
                return fmt_list, lang_code, "manual"

        # 6. Other auto-generated tracks (non-English, non-Hindi)
        for lang_code, fmt_list in auto_tracks.items():
            if fmt_list and not _is_translated_track(fmt_list):
                return fmt_list, lang_code, "generated"

    return None


def select_best_format(format_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Select the preferred format from the format list, preferring JSON3."""
    if not format_list:
        raise MalformedSubtitleDataError("Empty format list for subtitle track")

    for target_ext in _PREFERRED_FORMATS:
        for fmt in format_list:
            if fmt.get("ext", "").lower() == target_ext:
                return fmt

    # Fallback to the last format in the list
    return format_list[-1]


class YtDlpSubtitleExtractor:
    """yt-dlp-backed subtitle extractor."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    def extract_subtitles(self, video_url: str) -> RawSubtitleTrack:
        """Extract subtitles for a video without downloading video or audio."""
        import yt_dlp  # type: ignore[import-untyped]

        opts = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "skip_download": True,  # Hard requirement: never download video or audio
            "extract_flat": False,  # Required to resolve subtitle lists
            "socket_timeout": self.settings.subtitle_socket_timeout_seconds,
            "retries": 3,
            "ignoreerrors": False,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(video_url, download=False)
                except Exception as exc:
                    err_msg = str(exc)
                    err_lower = err_msg.lower()
                    # HTTP 429 / rate-limit: treat as a retryable extraction error,
                    # not a permanent video-unavailability condition.
                    if "429" in err_msg or "too many requests" in err_lower:
                        raise TranscriptExtractionError(
                            f"Rate-limited (HTTP 429) while fetching {video_url}: {err_msg}"
                        ) from exc
                    cat = classify_error_message(err_msg)
                    if cat in (
                        "PRIVATE",
                        "REMOVED",
                        "UNAVAILABLE",
                        "GEO_RESTRICTED",
                        "MEMBERS_ONLY",
                        "AGE_OR_AUTH_REQUIRED",
                    ):
                        raise VideoUnavailableError(video_url, err_msg) from exc
                    raise TranscriptExtractionError(
                        f"yt-dlp extraction failed for {video_url}: {err_msg}"
                    ) from exc

                if not info:
                    raise VideoUnavailableError(video_url, "No information returned by yt-dlp")

                # Check availability markers on extracted info
                title = str(info.get("title") or "")
                avail = str(info.get("availability") or "public")
                if title in ("[Private video]", "[Deleted video]") or avail == "private":
                    raise VideoUnavailableError(video_url, f"Video is unavailable: {title}")

                subtitles = info.get("subtitles") or {}
                auto_captions = info.get("automatic_captions") or {}

                selected = select_best_track(
                    subtitles=subtitles,
                    automatic_captions=auto_captions,
                    preferred_languages=self.settings.subtitle_languages,
                    prefer_manual=self.settings.subtitle_prefer_manual,
                )

                if selected is None:
                    raise CaptionsUnavailableError(f"No usable captions available for {video_url}")

                formats, lang, source = selected
                chosen_format = select_best_format(formats)
                ext = chosen_format.get("ext", "json3")

                content = chosen_format.get("data")
                if content is None:
                    stream_url = chosen_format.get("url")
                    if not stream_url:
                        raise MalformedSubtitleDataError(
                            f"Subtitle format has neither data nor url: {chosen_format}"
                        )
                    try:
                        resp = ydl.urlopen(stream_url)
                        content = resp.read().decode("utf-8", errors="replace")
                    except Exception as exc:
                        err_msg = str(exc)
                        err_lower = err_msg.lower()
                        if "429" in err_msg or "too many requests" in err_lower:
                            raise TranscriptExtractionError(
                                f"Rate-limited (HTTP 429) downloading subtitle stream: {err_msg}"
                            ) from exc
                        raise TranscriptExtractionError(
                            f"Failed to download subtitle stream: {exc}"
                        ) from exc

                return RawSubtitleTrack(
                    content=content,
                    format_name=ext,
                    language=lang,
                    source=source,
                )

        except (
            VideoUnavailableError,
            CaptionsUnavailableError,
            MalformedSubtitleDataError,
            TranscriptExtractionError,
        ):
            raise
        except Exception as exc:
            raise TranscriptExtractionError(
                f"Unexpected error during subtitle extraction: {exc}"
            ) from exc
