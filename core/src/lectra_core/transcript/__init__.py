"""Transcript acquisition and persistence package."""

from lectra_core.transcript.formats import (
    parse_json3,
    parse_subtitle_content,
    parse_vtt,
    parse_xml,
)
from lectra_core.transcript.models import (
    AudioDownloadError,
    CaptionsUnavailableError,
    MalformedSubtitleDataError,
    NonEnglishAudioError,
    TranscriptError,
    TranscriptExtractionError,
    TranscriptExtractionResult,
    TranscriptSegmentData,
    VideoUnavailableError,
    WhisperTranscriptionError,
)
from lectra_core.transcript.normalizer import clean_subtitle_text, normalize_timestamps
from lectra_core.transcript.service import (
    STAGE_TRANSCRIPT_ACQUISITION,
    PlaylistTranscriptResult,
    TranscriptService,
    VideoTranscriptSummary,
)
from lectra_core.transcript.whisper_transcriber import (
    AudioDownloaderProtocol,
    FasterWhisperTranscriber,
    WhisperModelManager,
    WhisperTranscriberProtocol,
    YtDlpAudioDownloader,
    resolve_whisper_device_and_compute_type,
)
from lectra_core.transcript.ytdlp_extractor import (
    RawSubtitleTrack,
    SubtitleExtractor,
    YtDlpSubtitleExtractor,
    select_best_format,
    select_best_track,
)

__all__ = [
    "AudioDownloadError",
    "AudioDownloaderProtocol",
    "CaptionsUnavailableError",
    "FasterWhisperTranscriber",
    "MalformedSubtitleDataError",
    "NonEnglishAudioError",
    "PlaylistTranscriptResult",
    "RawSubtitleTrack",
    "STAGE_TRANSCRIPT_ACQUISITION",
    "SubtitleExtractor",
    "TranscriptError",
    "TranscriptExtractionError",
    "TranscriptExtractionResult",
    "TranscriptSegmentData",
    "TranscriptService",
    "VideoTranscriptSummary",
    "VideoUnavailableError",
    "WhisperModelManager",
    "WhisperTranscriberProtocol",
    "WhisperTranscriptionError",
    "YtDlpAudioDownloader",
    "YtDlpSubtitleExtractor",
    "clean_subtitle_text",
    "normalize_timestamps",
    "parse_json3",
    "parse_subtitle_content",
    "parse_vtt",
    "parse_xml",
    "resolve_whisper_device_and_compute_type",
    "select_best_format",
    "select_best_track",
]
