"""Unit tests for Phase 3.2 local Whisper fallback transcription."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from lectra_core.config import Settings
from lectra_core.db.models import Playlist, ProcessingStage, Video
from lectra_core.db.session import get_db, get_engine, init_db
from lectra_core.repositories import transcript_repository
from lectra_core.transcript.models import (
    AudioDownloadError,
    CaptionsUnavailableError,
    NonEnglishAudioError,
    TranscriptSegmentData,
    VideoUnavailableError,
    WhisperTranscriptionError,
)
from lectra_core.transcript.service import TranscriptService
from lectra_core.transcript.whisper_transcriber import (
    FasterWhisperTranscriber,
    WhisperModelManager,
    YtDlpAudioDownloader,
    resolve_whisper_device_and_compute_type,
)
from sqlalchemy import select

from .mock_extractor import (
    SAMPLE_JSON3_ENGLISH,
    FakeSubtitleExtractor,
    FakeWhisperTranscriber,
)

# ---------------------------------------------------------------------------
# 1. Device and compute type resolution
# ---------------------------------------------------------------------------


def test_resolve_whisper_device_and_compute_type_explicit():
    dev, ctype = resolve_whisper_device_and_compute_type("cpu", "int8")
    assert dev == "cpu"
    assert ctype == "int8"

    dev, ctype = resolve_whisper_device_and_compute_type("cuda", "float16")
    assert dev == "cuda"
    assert ctype == "float16"


def test_resolve_whisper_device_and_compute_type_auto_with_cuda():
    with patch("ctranslate2.get_cuda_device_count", return_value=1):
        dev, ctype = resolve_whisper_device_and_compute_type("auto", "auto")
        assert dev == "cuda"
        assert ctype == "float16"


def test_resolve_whisper_device_and_compute_type_auto_without_cuda():
    with patch("ctranslate2.get_cuda_device_count", return_value=0):
        dev, ctype = resolve_whisper_device_and_compute_type("auto", "auto")
        assert dev == "cpu"
        assert ctype == "int8"


# ---------------------------------------------------------------------------
# 2. WhisperModelManager initialization and reuse
# ---------------------------------------------------------------------------


def test_whisper_model_manager_reuses_loaded_model():
    manager = WhisperModelManager()
    mock_model = MagicMock()

    with patch("faster_whisper.WhisperModel", return_value=mock_model) as mock_cls:
        m1 = manager.get_model("small.en", "cpu", "int8")
        assert m1 is mock_model
        assert mock_cls.call_count == 1

        # Re-fetching with same parameters must reuse cached model
        m2 = manager.get_model("small.en", "cpu", "int8")
        assert m2 is mock_model
        assert mock_cls.call_count == 1

        # Fetching with different model or device unloads and loads new model
        manager.get_model("tiny.en", "cpu", "int8")
        assert mock_cls.call_count == 2


def test_whisper_model_manager_cuda_fallback_to_cpu():
    manager = WhisperModelManager()
    mock_cpu_model = MagicMock()

    def _side_effect(*args, **kwargs):
        if kwargs.get("device") == "cuda":
            raise RuntimeError("CUDA driver error")
        return mock_cpu_model

    with patch("faster_whisper.WhisperModel", side_effect=_side_effect):
        model = manager.get_model("small.en", "cuda", "float16")
        assert model is mock_cpu_model
        assert manager._current_key == ("small.en", "cpu", "int8")


def test_whisper_model_manager_unload():
    manager = WhisperModelManager()
    manager._model = MagicMock()
    manager._current_key = ("small.en", "cpu", "int8")

    manager.unload_model()
    assert manager._model is None
    assert manager._current_key is None


# ---------------------------------------------------------------------------
# 3. AudioDownloader (audio only, no video, ffmpeg check, error handling)
# ---------------------------------------------------------------------------


def test_audio_downloader_ffmpeg_missing_raises_error(tmp_path):
    downloader = YtDlpAudioDownloader(Settings(_env_file=None))
    with patch("shutil.which", return_value=None):
        with pytest.raises(AudioDownloadError) as exc_info:
            downloader.download_audio("https://www.youtube.com/watch?v=dummy", tmp_path, "dummy")
        assert "FFmpeg is not installed" in str(exc_info.value)


def test_audio_downloader_invokes_yt_dlp_with_audio_only(tmp_path):
    downloader = YtDlpAudioDownloader(Settings(_env_file=None))

    # Pre-create the fake downloaded audio file so glob finds it
    fake_audio = tmp_path / "dummy.m4a"
    fake_audio.write_bytes(b"dummy audio content")

    fake_ydl = MagicMock()
    fake_ydl.__enter__ = MagicMock(return_value=fake_ydl)
    fake_ydl.__exit__ = MagicMock(return_value=False)

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("yt_dlp.YoutubeDL", return_value=fake_ydl) as mock_ydl_cls,
    ):
        result_path = downloader.download_audio(
            "https://www.youtube.com/watch?v=dummy", tmp_path, "dummy"
        )
        assert result_path == fake_audio

        opts = mock_ydl_cls.call_args[0][0]
        assert opts.get("format") == "bestaudio/best"
        # Confirm FFmpegExtractAudio postprocessor is configured
        postprocessors = opts.get("postprocessors", [])
        assert any(p.get("key") == "FFmpegExtractAudio" for p in postprocessors)


def test_audio_downloader_http_429_detected(tmp_path):
    downloader = YtDlpAudioDownloader(Settings(_env_file=None))
    fake_ydl = MagicMock()
    fake_ydl.__enter__ = MagicMock(return_value=fake_ydl)
    fake_ydl.__exit__ = MagicMock(return_value=False)
    fake_ydl.download.side_effect = Exception("HTTP Error 429: Too Many Requests")

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("yt_dlp.YoutubeDL", return_value=fake_ydl),
    ):
        with pytest.raises(AudioDownloadError) as exc_info:
            downloader.download_audio("https://www.youtube.com/watch?v=dummy", tmp_path, "dummy")
        assert exc_info.value.is_rate_limited is True
        assert "429" in str(exc_info.value)


def test_audio_downloader_unavailable_video(tmp_path):
    downloader = YtDlpAudioDownloader(Settings(_env_file=None))
    fake_ydl = MagicMock()
    fake_ydl.__enter__ = MagicMock(return_value=fake_ydl)
    fake_ydl.__exit__ = MagicMock(return_value=False)
    fake_ydl.download.side_effect = Exception("Video unavailable: This video is private")

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("yt_dlp.YoutubeDL", return_value=fake_ydl),
    ):
        with pytest.raises(VideoUnavailableError):
            downloader.download_audio("https://www.youtube.com/watch?v=dummy", tmp_path, "dummy")


# ---------------------------------------------------------------------------
# 4. FasterWhisperTranscriber (cleanup, segment normalization, non-English check)
# ---------------------------------------------------------------------------


def test_transcriber_cleans_up_audio_file_on_success(tmp_path):
    settings = Settings(_env_file=None, temp_audio_dir=tmp_path / "temp_audio")
    mock_downloader = MagicMock()

    created_audio_files = []

    def _fake_download(url, output_dir, yid):
        audio_file = output_dir / f"{yid}.m4a"
        audio_file.write_bytes(b"dummy audio")
        created_audio_files.append(audio_file)
        return audio_file

    mock_downloader.download_audio.side_effect = _fake_download

    # Mock Whisper model
    mock_seg = MagicMock()
    mock_seg.start = 0.0
    mock_seg.end = 2.5
    mock_seg.text = "Hello world from Whisper"

    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.language_probability = 0.99

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_seg], mock_info)

    mock_manager = MagicMock()
    mock_manager.get_model.return_value = mock_model

    transcriber = FasterWhisperTranscriber(
        settings=settings,
        downloader=mock_downloader,
        model_manager=mock_manager,
    )

    res = transcriber.transcribe_video("https://www.youtube.com/watch?v=test1", "test1")
    assert res.source == "whisper"
    assert res.language == "en"
    assert len(res.segments) == 1
    assert res.segments[0].text == "Hello world from Whisper"

    # Verify audio file and its parent temp dir were cleaned up
    assert len(created_audio_files) == 1
    assert not created_audio_files[0].exists()
    assert not created_audio_files[0].parent.exists()


def test_transcriber_cleans_up_audio_file_on_failure(tmp_path):
    settings = Settings(_env_file=None, temp_audio_dir=tmp_path / "temp_audio")
    mock_downloader = MagicMock()

    created_dirs = []

    def _fake_download(url, output_dir, yid):
        created_dirs.append(output_dir)
        audio_file = output_dir / f"{yid}.m4a"
        audio_file.write_bytes(b"dummy audio")
        return audio_file

    mock_downloader.download_audio.side_effect = _fake_download

    mock_model = MagicMock()
    mock_model.transcribe.side_effect = RuntimeError("Transcription engine failure")

    mock_manager = MagicMock()
    mock_manager.get_model.return_value = mock_model

    transcriber = FasterWhisperTranscriber(
        settings=settings,
        downloader=mock_downloader,
        model_manager=mock_manager,
    )

    with pytest.raises(RuntimeError):
        transcriber.transcribe_video("https://www.youtube.com/watch?v=test2", "test2")

    # Temp dir must have been cleaned up even after exception
    assert len(created_dirs) == 1
    assert not created_dirs[0].exists()


def test_transcriber_rejects_non_english_audio(tmp_path):
    settings = Settings(_env_file=None, temp_audio_dir=tmp_path / "temp_audio")
    mock_downloader = MagicMock()

    def _fake_download(url, output_dir, yid):
        f = output_dir / f"{yid}.m4a"
        f.write_bytes(b"dummy")
        return f

    mock_downloader.download_audio.side_effect = _fake_download

    mock_info = MagicMock()
    mock_info.language = "hi"
    mock_info.language_probability = 0.98

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], mock_info)

    mock_manager = MagicMock()
    mock_manager.get_model.return_value = mock_model

    transcriber = FasterWhisperTranscriber(
        settings=settings,
        downloader=mock_downloader,
        model_manager=mock_manager,
    )

    with pytest.raises(NonEnglishAudioError) as exc_info:
        transcriber.transcribe_video("https://www.youtube.com/watch?v=hindi_vid", "hindi_vid")

    assert exc_info.value.detected_language == "hi"
    assert exc_info.value.probability == 0.98


def test_transcriber_raises_when_no_segments_produced(tmp_path):
    settings = Settings(_env_file=None, temp_audio_dir=tmp_path / "temp_audio")
    mock_downloader = MagicMock()

    def _fake_download(url, output_dir, yid):
        f = output_dir / f"{yid}.m4a"
        f.write_bytes(b"dummy")
        return f

    mock_downloader.download_audio.side_effect = _fake_download

    mock_info = MagicMock()
    mock_info.language = "en"

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], mock_info)  # Empty iterator

    mock_manager = MagicMock()
    mock_manager.get_model.return_value = mock_model

    transcriber = FasterWhisperTranscriber(
        settings=settings,
        downloader=mock_downloader,
        model_manager=mock_manager,
    )

    with pytest.raises(WhisperTranscriptionError):
        transcriber.transcribe_video("https://www.youtube.com/watch?v=silent_vid", "silent_vid")


# ---------------------------------------------------------------------------
# 5. Pipeline Integration (Caption-first, Whisper fallback, error transitions)
# ---------------------------------------------------------------------------


@pytest.fixture
def whisper_service_env(tmp_path):
    db_file = tmp_path / "whisper_test.db"
    artifacts_dir = tmp_path / "artifacts"
    temp_audio_dir = tmp_path / "temp_audio"
    settings = Settings(
        database_url=f"sqlite:///{db_file}",
        data_dir=tmp_path,
        artifacts_dir=artifacts_dir,
        temp_audio_dir=temp_audio_dir,
    )
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)

    fake_extractor = FakeSubtitleExtractor()
    fake_transcriber = FakeWhisperTranscriber()
    service = TranscriptService(
        settings=settings,
        extractor=fake_extractor,
        transcriber=fake_transcriber,
    )

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_whisper_test",
            url="https://www.youtube.com/playlist?list=PL_whisper_test",
            title="Whisper Test Playlist",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_with_captions",
            title="Captioned Video",
            url="https://www.youtube.com/watch?v=vid_with_captions",
            position=0,
            status="DISCOVERED",
        )
        v2 = Video(
            playlist_id=pl.id,
            youtube_id="vid_without_captions",
            title="Uncaptioned Video",
            url="https://www.youtube.com/watch?v=vid_without_captions",
            position=1,
            status="DISCOVERED",
        )
        v3 = Video(
            playlist_id=pl.id,
            youtube_id="vid_hindi_speech",
            title="Hindi Speech Video",
            url="https://www.youtube.com/watch?v=vid_hindi_speech",
            position=2,
            status="DISCOVERED",
        )
        v4 = Video(
            playlist_id=pl.id,
            youtube_id="vid_whisper_fail",
            title="Failing Video",
            url="https://www.youtube.com/watch?v=vid_whisper_fail",
            position=3,
            status="DISCOVERED",
        )
        session.add_all([v1, v2, v3, v4])
        session.commit()
        pl_id = pl.id

    return settings, service, fake_extractor, fake_transcriber, pl_id


def test_caption_first_behavior_whisper_not_invoked(whisper_service_env):
    """When English captions are available, caption extraction is used and Whisper is NOT run."""
    settings, service, extractor, transcriber, _ = whisper_service_env
    url = "https://www.youtube.com/watch?v=vid_with_captions"
    extractor.set_response(url, SAMPLE_JSON3_ENGLISH, "json3", "en", "manual")

    with next(get_db(settings)) as session:
        video = session.scalars(
            select(Video).where(Video.youtube_id == "vid_with_captions")
        ).first()
        summary = service.process_video(session, video)
        session.commit()

        assert summary.status == "TRANSCRIPT_READY"
        assert summary.source == "manual"
        assert summary.language == "en"
        # Whisper transcriber must NOT have been called
        assert transcriber.call_count.get(url, 0) == 0


def test_whisper_fallback_when_captions_unavailable(whisper_service_env):
    """When English captions are missing, Whisper fallback runs and produces TRANSCRIPT_READY."""
    settings, service, extractor, transcriber, _ = whisper_service_env
    url = "https://www.youtube.com/watch?v=vid_without_captions"
    extractor.set_error(url, CaptionsUnavailableError("No subtitles found"))

    custom_segments = [
        TranscriptSegmentData(
            segment_index=0,
            start_seconds=1.0,
            end_seconds=4.0,
            duration_seconds=3.0,
            text="First segment from local Whisper.",
            language="en",
            source="whisper",
        ),
        TranscriptSegmentData(
            segment_index=1,
            start_seconds=4.0,
            end_seconds=7.5,
            duration_seconds=3.5,
            text="Second segment from local Whisper.",
            language="en",
            source="whisper",
        ),
    ]
    transcriber.set_response(url, "vid_without_captions", custom_segments, language="en")

    with next(get_db(settings)) as session:
        video = session.scalars(
            select(Video).where(Video.youtube_id == "vid_without_captions")
        ).first()
        summary = service.process_video(session, video)
        session.commit()

        assert summary.status == "TRANSCRIPT_READY"
        assert summary.source == "whisper"
        assert summary.language == "en"
        assert summary.segment_count == 2

        # Verify database records
        assert video.status == "TRANSCRIPT_READY"
        saved = transcript_repository.get_by_video_id(session, video.id)
        assert len(saved) == 2
        assert saved[0].source == "whisper"
        assert saved[0].text == "First segment from local Whisper."
        assert saved[1].start_seconds == 4.0

        # Verify ProcessingStage
        stage = session.scalars(
            select(ProcessingStage).where(ProcessingStage.video_id == video.id)
        ).first()
        assert stage.status == "COMPLETED"
        assert stage.artifact_path is not None
        assert Path(stage.artifact_path).exists()


def test_whisper_non_english_audio_marks_needs_transcription(whisper_service_env):
    """When Whisper detects non-English speech, mark NEEDS_TRANSCRIPTION (no translation)."""
    settings, service, extractor, transcriber, _ = whisper_service_env
    url = "https://www.youtube.com/watch?v=vid_hindi_speech"
    extractor.set_error(url, CaptionsUnavailableError("No subtitles"))
    transcriber.set_error(url, NonEnglishAudioError("hi", 0.97))

    with next(get_db(settings)) as session:
        video = session.scalars(select(Video).where(Video.youtube_id == "vid_hindi_speech")).first()
        summary = service.process_video(session, video)
        session.commit()

        assert summary.status == "NEEDS_TRANSCRIPTION"
        assert summary.error_category == "NON_ENGLISH_AUDIO"
        assert video.status == "NEEDS_TRANSCRIPTION"

        stage = session.scalars(
            select(ProcessingStage).where(ProcessingStage.video_id == video.id)
        ).first()
        assert stage.status == "SKIPPED"
        assert stage.error_category == "NON_ENGLISH_AUDIO"

        # No segments should be saved
        assert transcript_repository.has_transcripts(session, video.id) is False


def test_whisper_download_failure_marks_extraction_failed(whisper_service_env):
    """When audio download fails, mark EXTRACTION_FAILED so the worker can retry."""
    settings, service, extractor, transcriber, _ = whisper_service_env
    url = "https://www.youtube.com/watch?v=vid_whisper_fail"
    extractor.set_error(url, CaptionsUnavailableError("No subtitles"))
    transcriber.set_error(url, AudioDownloadError("Network connection reset"))

    with next(get_db(settings)) as session:
        video = session.scalars(select(Video).where(Video.youtube_id == "vid_whisper_fail")).first()
        summary = service.process_video(session, video)
        session.commit()

        assert summary.status == "EXTRACTION_FAILED"
        assert summary.error_category == "WHISPER_FAILED"
        assert video.status == "EXTRACTION_FAILED"

        stage = session.scalars(
            select(ProcessingStage).where(ProcessingStage.video_id == video.id)
        ).first()
        assert stage.status == "FAILED"


def test_idempotent_whisper_persistence(whisper_service_env):
    """Re-processing a video already TRANSCRIPT_READY via Whisper skips redundant transcription."""
    settings, service, extractor, transcriber, _ = whisper_service_env
    url = "https://www.youtube.com/watch?v=vid_without_captions"
    extractor.set_error(url, CaptionsUnavailableError("No subtitles"))

    with next(get_db(settings)) as session:
        video = session.scalars(
            select(Video).where(Video.youtube_id == "vid_without_captions")
        ).first()
        res1 = service.process_video(session, video)
        session.commit()
        assert res1.status == "TRANSCRIPT_READY"
        first_calls = transcriber.call_count[url]

        # Second call
        res2 = service.process_video(session, video)
        session.commit()
        assert res2.status == "ALREADY_DONE"
        # Transcriber must not have been invoked again
        assert transcriber.call_count[url] == first_calls
