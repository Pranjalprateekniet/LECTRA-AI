"""Local Whisper ASR fallback using faster-whisper.

Downloads audio streams only (never video), executes speech-to-text
transcription locally, enforces the English-only policy, normalizes timestamps
and text, and cleans up temporary audio files immediately after transcription.
"""

import gc
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple

from lectra_core.config import Settings, get_settings
from lectra_core.discovery.ytdlp_client import classify_error_message
from lectra_core.logging import get_logger
from lectra_core.transcript.models import (
    AudioDownloadError,
    NonEnglishAudioError,
    TranscriptExtractionResult,
    TranscriptSegmentData,
    VideoUnavailableError,
    WhisperTranscriptionError,
)
from lectra_core.transcript.normalizer import clean_subtitle_text, normalize_timestamps

logger = get_logger("lectra.transcript.whisper")


def resolve_whisper_device_and_compute_type(
    device_setting: str,
    compute_type_setting: str,
) -> Tuple[str, str]:
    """Resolve the execution device and compute type based on configuration and hardware."""
    dev = device_setting.lower().strip()
    ctype = compute_type_setting.lower().strip()

    if dev == "auto":
        try:
            import ctranslate2  # type: ignore[import-untyped]

            cuda_count = ctranslate2.get_cuda_device_count()
            resolved_dev = "cuda" if cuda_count > 0 else "cpu"
        except Exception:
            resolved_dev = "cpu"
    elif dev in ("cuda", "gpu"):
        resolved_dev = "cuda"
    else:
        resolved_dev = "cpu"

    if ctype == "auto":
        resolved_ctype = "float16" if resolved_dev == "cuda" else "int8"
    else:
        resolved_ctype = ctype

    return resolved_dev, resolved_ctype


class WhisperModelManager:
    """Manages cached faster-whisper model instances to avoid redundant reloads."""

    _instance: Optional["WhisperModelManager"] = None

    def __init__(self):
        self._model: Any = None
        self._current_key: Optional[Tuple[str, str, str]] = None

    @classmethod
    def get_instance(cls) -> "WhisperModelManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_model(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        download_root: Optional[Path] = None,
    ) -> Any:
        """Retrieve a loaded WhisperModel instance, initializing or replacing if needed."""
        target_key = (model_name, device, compute_type)
        if self._model is not None and self._current_key == target_key:
            return self._model

        # Unload prior model first to prevent multiple models in memory/VRAM
        self.unload_model()

        from faster_whisper import WhisperModel  # type: ignore[import-untyped]

        try:
            logger.info(
                "Loading faster-whisper model",
                extra={"model": model_name, "device": device, "compute_type": compute_type},
            )
            model = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                download_root=str(download_root) if download_root else None,
            )

            # If CUDA was requested, verify that CUDA runtime libraries (libcublas, cudnn)
            # are loadable by executing a lightweight probe before accepting the model.
            if device == "cuda":
                import numpy as np

                probe = np.zeros(1600, dtype=np.float32)
                _segs, _ = model.transcribe(probe, language="en")
                list(_segs)

            self._model = model
            self._current_key = target_key
            return model
        except Exception as exc:
            if device == "cuda":
                logger.warning(
                    f"CUDA initialization failed for faster-whisper ({exc}). "
                    f"Falling back to CPU int8.",
                    extra={"error": str(exc)},
                )
                self.unload_model()
                fallback_device = "cpu"
                fallback_compute = "int8"
                model = WhisperModel(
                    model_name,
                    device=fallback_device,
                    compute_type=fallback_compute,
                    download_root=str(download_root) if download_root else None,
                )
                self._model = model
                self._current_key = (model_name, fallback_device, fallback_compute)
                return model
            raise

    def unload_model(self) -> None:
        """Release Whisper model and clean up associated memory/VRAM."""
        if self._model is not None:
            logger.info("Unloading faster-whisper model to free resources")
            del self._model
            self._model = None
            self._current_key = None
            gc.collect()
            try:
                import torch  # type: ignore[import-untyped]

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass


class AudioDownloaderProtocol(Protocol):
    """Protocol for audio downloaders."""

    def download_audio(self, video_url: str, output_dir: Path, youtube_id: str) -> Path: ...


class YtDlpAudioDownloader:
    """yt-dlp-backed audio downloader extracting audio streams without video."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    def download_audio(self, video_url: str, output_dir: Path, youtube_id: str) -> Path:
        """Download audio only from a YouTube video into output_dir.

        Raises:
            AudioDownloadError: On network, rate limit, timeout, or missing FFmpeg.
            VideoUnavailableError: If video is deleted, private, or restricted.
        """
        # Ensure FFmpeg is available on the system PATH
        if not shutil.which("ffmpeg"):
            raise AudioDownloadError(
                "FFmpeg is not installed or not found on system PATH. "
                "FFmpeg is required to extract audio for transcription."
            )

        import yt_dlp  # type: ignore[import-untyped]

        out_template = str(output_dir / f"{youtube_id}.%(ext)s")
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                }
            ],
            "socket_timeout": self.settings.subtitle_socket_timeout_seconds,
            "retries": 2,
            "ignoreerrors": False,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    ydl.download([video_url])
                except Exception as exc:
                    err_msg = str(exc)
                    err_lower = err_msg.lower()

                    if "429" in err_msg or "too many requests" in err_lower:
                        raise AudioDownloadError(
                            f"Rate-limited (HTTP 429) downloading audio for {video_url}: {err_msg}",
                            is_rate_limited=True,
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
                        raise VideoUnavailableError(youtube_id, err_msg) from exc

                    raise AudioDownloadError(
                        f"Failed to download audio for {youtube_id}: {err_msg}"
                    ) from exc

            # Locate the extracted audio file in output_dir
            candidates = list(output_dir.glob(f"{youtube_id}.*"))
            if not candidates:
                raise AudioDownloadError(
                    f"No audio file found in {output_dir} after download for {youtube_id}"
                )

            return candidates[0]

        except (AudioDownloadError, VideoUnavailableError):
            raise
        except Exception as exc:
            raise AudioDownloadError(
                f"Unexpected error downloading audio for {youtube_id}: {exc}"
            ) from exc


class WhisperTranscriberProtocol(Protocol):
    """Protocol for Whisper transcription providers."""

    def transcribe_video(self, video_url: str, youtube_id: str) -> TranscriptExtractionResult: ...


class FasterWhisperTranscriber:
    """Orchestrates audio download, faster-whisper transcription, and segment conversion."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        downloader: Optional[AudioDownloaderProtocol] = None,
        model_manager: Optional[WhisperModelManager] = None,
    ):
        self.settings = settings or get_settings()
        self.downloader: AudioDownloaderProtocol = downloader or YtDlpAudioDownloader(self.settings)
        self.model_manager = model_manager or WhisperModelManager.get_instance()

    def transcribe_video(self, video_url: str, youtube_id: str) -> TranscriptExtractionResult:
        """Download audio, transcribe with faster-whisper, and clean up temporary audio files.

        Guarantees:
        - Audio is downloaded to an isolated temporary directory.
        - Audio files are deleted in a finally block regardless of success or failure.
        - Output language is verified to be English.
        - Segments are normalized with millisecond precision timestamps.
        """
        self.settings.temp_audio_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(
            tempfile.mkdtemp(prefix=f"audio_{youtube_id}_", dir=self.settings.temp_audio_dir)
        )

        try:
            logger.info("Downloading audio for Whisper fallback", extra={"video_id": youtube_id})
            audio_path = self.downloader.download_audio(video_url, temp_dir, youtube_id)

            device, compute_type = resolve_whisper_device_and_compute_type(
                self.settings.whisper_device,
                self.settings.whisper_compute_type,
            )

            model = self.model_manager.get_model(
                self.settings.whisper_model_name,
                device,
                compute_type,
                self.settings.model_cache_dir,
            )

            start_time = time.perf_counter()
            logger.info(
                "Starting faster-whisper transcription",
                extra={
                    "video_id": youtube_id,
                    "model": self.settings.whisper_model_name,
                    "device": device,
                    "compute_type": compute_type,
                    "beam_size": self.settings.whisper_beam_size,
                },
            )

            try:
                segments_iter, info = model.transcribe(
                    str(audio_path),
                    language="en",
                    task="transcribe",
                    beam_size=self.settings.whisper_beam_size,
                    vad_filter=True,
                )
                raw_segments = list(segments_iter)
            except Exception as exc:
                exc_lower = str(exc).lower()
                is_cuda_err = any(k in exc_lower for k in ("cuda", "libcublas", "out of memory"))
                if is_cuda_err:
                    logger.warning(
                        f"CUDA transcription runtime failed ({exc}). Falling back to CPU int8.",
                        extra={"error": str(exc)},
                    )
                    self.model_manager.unload_model()
                    model = self.model_manager.get_model(
                        self.settings.whisper_model_name,
                        "cpu",
                        "int8",
                        self.settings.model_cache_dir,
                    )
                    segments_iter, info = model.transcribe(
                        str(audio_path),
                        language="en",
                        task="transcribe",
                        beam_size=self.settings.whisper_beam_size,
                        vad_filter=True,
                    )
                    raw_segments = list(segments_iter)
                else:
                    raise

            # Enforce English-only policy: detect non-English spoken content
            detected_lang = getattr(info, "language", "en")
            if detected_lang != "en":
                prob = getattr(info, "language_probability", 0.0)
                raise NonEnglishAudioError(detected_language=detected_lang, probability=prob)

            segments: List[TranscriptSegmentData] = []
            for seg in raw_segments:
                cleaned = clean_subtitle_text(seg.text)
                if not cleaned:
                    continue

                start_sec, end_sec, dur_sec = normalize_timestamps(
                    seg.start, seg.end, seg.end - seg.start
                )
                segments.append(
                    TranscriptSegmentData(
                        segment_index=len(segments),
                        start_seconds=start_sec,
                        end_seconds=end_sec,
                        duration_seconds=dur_sec,
                        text=cleaned,
                        language="en",
                        source="whisper",
                    )
                )

            elapsed = round(time.perf_counter() - start_time, 2)

            if not segments:
                raise WhisperTranscriptionError(
                    f"Whisper produced no valid text segments for video {youtube_id}"
                )

            logger.info(
                "Whisper transcription completed successfully",
                extra={
                    "video_id": youtube_id,
                    "duration_seconds": elapsed,
                    "device": device,
                    "model": self.settings.whisper_model_name,
                    "segment_count": len(segments),
                },
            )

            return TranscriptExtractionResult(
                youtube_id=youtube_id,
                language="en",
                source="whisper",
                segments=segments,
            )

        finally:
            # Guarantee prompt deletion of temporary audio files on success or failure
            shutil.rmtree(temp_dir, ignore_errors=True)
