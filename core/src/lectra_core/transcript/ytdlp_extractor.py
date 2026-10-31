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
    preferred_languages: List[str],
    prefer_manual: bool = True,
    allow_non_english: bool = False,
) -> Optional[Tuple[List[Dict[str, Any]], str, str]]:
    """Select the best available subtitle track according to preferences.

    Only tracks whose language code matches one of *preferred_languages* (exact
    or prefix match) are considered.  Auto-translated tracks (containing `tlang=`)
    are skipped to respect the English-only and no-translation requirements.

    Returns: (format_list, selected_language, source_type) or None if no
    matching captions exist.
    """
    manual_tracks = subtitles or {}
    auto_tracks = automatic_captions or {}

    def _find_matching_track(
        tracks: Dict[str, List[Dict[str, Any]]],
    ) -> Optional[Tuple[List[Dict[str, Any]], str]]:
        if not tracks:
            return None
        # 1. Exact match on preferred languages in order
        for pref in preferred_languages:
            pref_lower = pref.lower().strip()
            for lang_code, fmt_list in tracks.items():
                if lang_code.lower() == pref_lower and fmt_list:
                    if _is_translated_track(fmt_list):
                        continue
                    return fmt_list, lang_code

        # 2. Prefix match on preferred languages in order (e.g., 'en-US', 'en-GB')
        for pref in preferred_languages:
            pref_lower = pref.lower().strip()
            for lang_code, fmt_list in tracks.items():
                lower_code = lang_code.lower()
                if (
                    lower_code.startswith(f"{pref_lower}-")
                    or lower_code.startswith(f"{pref_lower}.")
                ) and fmt_list:
                    if _is_translated_track(fmt_list):
                        continue
                    return fmt_list, lang_code

        # No match for any preferred language — do NOT fall back to arbitrary language.
        return None

    if prefer_manual:
        manual_match = _find_matching_track(manual_tracks)
        if manual_match:
            return manual_match[0], manual_match[1], "manual"

        auto_match = _find_matching_track(auto_tracks)
        if auto_match:
            return auto_match[0], auto_match[1], "generated"
    else:
        auto_match = _find_matching_track(auto_tracks)
        if auto_match:
            return auto_match[0], auto_match[1], "generated"

        manual_match = _find_matching_track(manual_tracks)
        if manual_match:
            return manual_match[0], manual_match[1], "manual"

    # 3. If English subtitles are unavailable and allow_non_english is enabled,
    # check for available non-English subtitles as translation input.
    if allow_non_english:
        for lang_code, fmt_list in manual_tracks.items():
            if fmt_list and not _is_translated_track(fmt_list):
                return fmt_list, lang_code, "manual"

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
