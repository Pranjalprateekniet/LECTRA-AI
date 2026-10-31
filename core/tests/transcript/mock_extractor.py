"""Mock subtitle extractors and fixtures for Phase 3.1 unit tests."""

from typing import Any, Dict, Union

from lectra_core.transcript.models import (
    CaptionsUnavailableError,
    TranscriptExtractionResult,
    TranscriptSegmentData,
)
from lectra_core.transcript.ytdlp_extractor import RawSubtitleTrack

SAMPLE_JSON3_ENGLISH = {
    "wireMagic": "pb3",
    "events": [
        {
            "tStartMs": 0,
            "dDurationMs": 2500,
            "segs": [{"utf8": "Hello &amp; welcome to the course."}],
        },
        {
            "tStartMs": 2500,
            "dDurationMs": 3100,
            "segs": [{"utf8": "Today we will study <b>binary search</b>.\n"}],
        },
        {
            "tStartMs": 5600,
            "dDurationMs": 2000,
            "segs": [{"utf8": "Let&#39;s start with time complexity: O(log N)."}],
        },
    ],
}

SAMPLE_JSON3_HINDI = {
    "wireMagic": "pb3",
    "events": [
        {
            "tStartMs": 1000,
            "dDurationMs": 3000,
            "segs": [{"utf8": "नमस्ते दोस्तों, इस वीडियो में हम ऐरे के बारे में सीखेंगे।"}],
        },
        {
            "tStartMs": 4000,
            "dDurationMs": 2500,
            "segs": [{"utf8": "यह एक बहुत महत्वपूर्ण विषय है।"}],
        },
    ],
}

SAMPLE_VTT_ENGLISH = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.500
Hello &amp; welcome to the revision session.

00:00:03.500 --> 00:00:06.800 align:start position:0%
<c.colorCCCCCC>Today we discuss dynamic programming.</c>

00:00:07.000 --> 00:00:10.000
Remember to review memoization.
"""

SAMPLE_XML_ENGLISH = """<?xml version="1.0" encoding="utf-8" ?>
<transcript>
  <text start="1.5" dur="2.5">Welcome to the &quot;lecture&quot;</text>
  <text start="4.0" dur="3.0">We are learning Python &amp; algorithms</text>
</transcript>
"""


class FakeSubtitleExtractor:
    """Configurable in-memory subtitle extractor for unit tests."""

    def __init__(self):
        self.responses: Dict[str, Union[RawSubtitleTrack, Exception]] = {}
        self.call_count: Dict[str, int] = {}

    def set_response(
        self,
        video_url: str,
        content: Union[str, Dict[str, Any]],
        format_name: str = "json3",
        language: str = "en",
        source: str = "manual",
    ) -> None:
        self.responses[video_url] = RawSubtitleTrack(
            content=content,
            format_name=format_name,
            language=language,
            source=source,
        )

    def set_error(self, video_url: str, exception: Exception) -> None:
        self.responses[video_url] = exception

    def extract_subtitles(self, video_url: str) -> RawSubtitleTrack:
        self.call_count[video_url] = self.call_count.get(video_url, 0) + 1
        res = self.responses.get(video_url)

        if res is None:
            raise CaptionsUnavailableError(f"No captions configured for {video_url}")

        if isinstance(res, Exception):
            raise res

        return res


class FakeWhisperTranscriber:
    """Configurable in-memory Whisper transcriber for unit tests."""

    def __init__(self):
        self.responses: Dict[str, Union[TranscriptExtractionResult, Exception]] = {}
        self.call_count: Dict[str, int] = {}

    def set_response(
        self,
        video_url: str,
        youtube_id: str,
        segments: list[TranscriptSegmentData],
        language: str = "en",
    ) -> None:
        self.responses[video_url] = TranscriptExtractionResult(
            youtube_id=youtube_id,
            language=language,
            source="whisper",
            segments=segments,
        )

    def set_error(self, video_url: str, exception: Exception) -> None:
        self.responses[video_url] = exception

    def transcribe_video(self, video_url: str, youtube_id: str) -> TranscriptExtractionResult:
        self.call_count[video_url] = self.call_count.get(video_url, 0) + 1
        res = self.responses.get(video_url)

        if res is None:
            # Default mock transcription with 2 segments
            return TranscriptExtractionResult(
                youtube_id=youtube_id,
                language="en",
                source="whisper",
                segments=[
                    TranscriptSegmentData(
                        segment_index=0,
                        start_seconds=0.0,
                        end_seconds=3.5,
                        duration_seconds=3.5,
                        text="This is a Whisper fallback segment.",
                        language="en",
                        source="whisper",
                    ),
                    TranscriptSegmentData(
                        segment_index=1,
                        start_seconds=3.5,
                        end_seconds=7.0,
                        duration_seconds=3.5,
                        text="Second Whisper transcribed sentence.",
                        language="en",
                        source="whisper",
                    ),
                ],
            )

        if isinstance(res, Exception):
            raise res

        return res
