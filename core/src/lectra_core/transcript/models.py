"""Data models and custom exceptions for transcript extraction and normalization."""

from dataclasses import dataclass
from typing import List


class TranscriptError(Exception):
    """Base exception for transcript extraction and processing."""


class CaptionsUnavailableError(TranscriptError):
    """Raised when a video has no usable manual or automatically generated captions."""


class VideoUnavailableError(TranscriptError):
    """Raised when a video is private, deleted, copyright-blocked, or inaccessible."""

    def __init__(self, youtube_id: str, reason: str):
        self.youtube_id = youtube_id
        self.reason = reason
        super().__init__(f"Video '{youtube_id}' is unavailable: {reason}")


class TranscriptExtractionError(TranscriptError):
    """Raised when a transient extraction failure occurs (network, rate limit, timeout)."""


class MalformedSubtitleDataError(TranscriptError):
    """Raised when subtitle format data cannot be parsed or lacks valid timing/text."""


class AudioDownloadError(TranscriptError):
    """Raised when downloading audio-only stream fails (network, 429, missing ffmpeg, etc.)."""

    def __init__(self, message: str, is_rate_limited: bool = False):
        self.is_rate_limited = is_rate_limited
        super().__init__(message)


class NonEnglishAudioError(TranscriptError):
    """Raised when Whisper detects that the spoken audio is not English."""

    def __init__(self, detected_language: str, probability: float = 0.0):
        self.detected_language = detected_language
        self.probability = probability
        super().__init__(
            f"Detected non-English audio language '{detected_language}' "
            f"(probability: {probability:.2f}). English-only policy strictly enforced."
        )


class WhisperTranscriptionError(TranscriptError):
    """Raised when local Whisper transcription fails or returns invalid/empty output."""


@dataclass(frozen=True)
class TranscriptSegmentData:
    """Normalized internal representation of a transcript segment."""

    segment_index: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    text: str
    language: str
    source: str  # "manual" | "generated" | "whisper"


@dataclass(frozen=True)
class TranscriptExtractionResult:
    """Result of extracting and normalizing transcripts for a video."""

    youtube_id: str
    language: str
    source: str  # "manual" | "generated" | "whisper"
    segments: List[TranscriptSegmentData]
