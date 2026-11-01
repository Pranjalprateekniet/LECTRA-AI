"""Unit tests for subtitle track and format selection logic (English-only extraction)."""

from unittest.mock import MagicMock, patch

import pytest
from lectra_core.transcript.models import TranscriptExtractionError
from lectra_core.transcript.ytdlp_extractor import (
    YtDlpSubtitleExtractor,
    select_best_format,
    select_best_track,
)

# ---------------------------------------------------------------------------
# select_best_track — happy paths
# ---------------------------------------------------------------------------


def test_select_best_track_prefers_auto_english_as_primary():
    """English auto-generated captions are preferred as the primary source."""
    subtitles = {
        "en": [{"ext": "json3", "url": "https://sub.test/manual_en"}],
    }
    automatic = {
        "en": [{"ext": "json3", "url": "https://sub.test/auto_en"}],
    }

    formats, lang, source = select_best_track(
        subtitles=subtitles,
        automatic_captions=automatic,
        preferred_languages=["en"],
    )
    assert source == "generated"
    assert lang == "en"
    assert formats[0]["url"] == "https://sub.test/auto_en"


def test_select_best_track_uses_manual_when_auto_absent():
    subtitles = {
        "en": [{"ext": "json3", "url": "https://sub.test/manual_en"}],
    }
    automatic = {}

    formats, lang, source = select_best_track(
        subtitles=subtitles,
        automatic_captions=automatic,
        preferred_languages=["en"],
    )
    assert source == "manual"
    assert lang == "en"
    assert formats[0]["url"] == "https://sub.test/manual_en"


def test_select_best_track_matches_en_us_prefix():
    """'en-US' should match when preferred language is 'en'."""
    subtitles = {}
    automatic = {
        "en-US": [{"ext": "json3", "url": "https://sub.test/auto_en_us"}],
    }

    formats, lang, source = select_best_track(
        subtitles=subtitles,
        automatic_captions=automatic,
        preferred_languages=["en"],
        prefer_manual=True,
    )
    assert lang == "en-US"
    assert source == "generated"


# ---------------------------------------------------------------------------
# select_best_track — Captions-first priority and multi-language support
# ---------------------------------------------------------------------------


def test_select_best_track_selects_hindi_when_english_unavailable():
    """When English captions are unavailable, selects best available Hindi caption track."""
    subtitles = {
        "es": [{"ext": "json3", "url": "https://sub.test/manual_es"}],
    }
    automatic = {
        "hi": [{"ext": "json3", "url": "https://sub.test/auto_hi"}],
    }

    result = select_best_track(
        subtitles=subtitles,
        automatic_captions=automatic,
        preferred_languages=["en"],
    )
    assert result is not None
    formats, lang, source = result
    assert lang == "hi"
    assert source == "generated"
    assert formats[0]["url"] == "https://sub.test/auto_hi"


def test_select_best_track_no_captions_returns_none():
    result = select_best_track(
        subtitles={},
        automatic_captions={},
        preferred_languages=["en"],
    )
    assert result is None


def test_select_best_track_returns_none_when_non_english_explicitly_disallowed():
    """Hindi-only auto-generated captions return None when allow_non_english=False."""
    result = select_best_track(
        subtitles={},
        automatic_captions={
            "hi": [{"ext": "json3", "url": "https://sub.test/hi"}],
        },
        preferred_languages=["en"],
        allow_non_english=False,
    )
    assert result is None


def test_select_best_track_ignores_auto_translated_en_track():
    """Tracks that are auto-translated to English (tlang=en) must be ignored."""
    result = select_best_track(
        subtitles={},
        automatic_captions={
            "en": [
                {
                    "ext": "json3",
                    "url": "https://www.youtube.com/api/timedtext?lang=hi&tlang=en&fmt=json3",
                }
            ],
        },
        preferred_languages=["en"],
        prefer_manual=True,
    )
    assert result is None


# ---------------------------------------------------------------------------
# select_best_format
# ---------------------------------------------------------------------------


def test_select_best_format_prefers_json3():
    fmt_list = [
        {"ext": "vtt", "url": "https://sub.test/vtt"},
        {"ext": "json3", "url": "https://sub.test/json3"},
        {"ext": "srv1", "url": "https://sub.test/srv1"},
    ]
    chosen = select_best_format(fmt_list)
    assert chosen["ext"] == "json3"
    assert chosen["url"] == "https://sub.test/json3"


def test_select_best_format_fallback_when_json3_missing():
    fmt_list = [
        {"ext": "ttml", "url": "https://sub.test/ttml"},
        {"ext": "vtt", "url": "https://sub.test/vtt"},
    ]
    chosen = select_best_format(fmt_list)
    assert chosen["ext"] == "vtt"


# ---------------------------------------------------------------------------
# HTTP 429 / rate-limit handling
# ---------------------------------------------------------------------------


def test_http_429_raises_extraction_error_not_unavailable_error():
    """yt-dlp raising a 429 error must surface as TranscriptExtractionError (retryable)."""
    from lectra_core.config import Settings
    from lectra_core.transcript.models import VideoUnavailableError

    settings = Settings(_env_file=None)
    extractor = YtDlpSubtitleExtractor(settings=settings)

    fake_exc = Exception("HTTP Error 429: Too Many Requests")

    fake_ydl = MagicMock()
    fake_ydl.__enter__ = MagicMock(return_value=fake_ydl)
    fake_ydl.__exit__ = MagicMock(return_value=False)
    fake_ydl.extract_info.side_effect = fake_exc

    with patch("yt_dlp.YoutubeDL", return_value=fake_ydl):
        with pytest.raises(TranscriptExtractionError) as exc_info:
            extractor.extract_subtitles("https://www.youtube.com/watch?v=dummy")

    assert "429" in str(exc_info.value) or "Rate-limited" in str(exc_info.value)

    # Must NOT be a VideoUnavailableError
    assert not isinstance(exc_info.value, VideoUnavailableError)


def test_too_many_requests_text_also_raises_extraction_error():
    """'Too Many Requests' in error text (without numeric 429) must also be retryable."""
    from lectra_core.config import Settings

    settings = Settings(_env_file=None)
    extractor = YtDlpSubtitleExtractor(settings=settings)

    fake_exc = Exception("too many requests, please slow down")

    fake_ydl = MagicMock()
    fake_ydl.__enter__ = MagicMock(return_value=fake_ydl)
    fake_ydl.__exit__ = MagicMock(return_value=False)
    fake_ydl.extract_info.side_effect = fake_exc

    with patch("yt_dlp.YoutubeDL", return_value=fake_ydl):
        with pytest.raises(TranscriptExtractionError):
            extractor.extract_subtitles("https://www.youtube.com/watch?v=dummy")
