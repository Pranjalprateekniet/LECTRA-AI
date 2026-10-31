"""Comprehensive unit tests for TranscriptService (Phase 3.1 requirements)."""

from pathlib import Path

import pytest
from lectra_core.config import Settings
from lectra_core.db.models import Playlist, ProcessingStage, Video
from lectra_core.db.session import get_db, get_engine, init_db
from lectra_core.repositories import transcript_repository
from lectra_core.transcript.models import (
    CaptionsUnavailableError,
    NonEnglishAudioError,
    TranscriptExtractionError,
    VideoUnavailableError,
)
from lectra_core.transcript.service import TranscriptService
from sqlalchemy import select

from .mock_extractor import (
    SAMPLE_JSON3_ENGLISH,
    SAMPLE_VTT_ENGLISH,
    FakeSubtitleExtractor,
    FakeWhisperTranscriber,
)


@pytest.fixture
def service_env(tmp_path):
    db_file = tmp_path / "service_test.db"
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
    # For uncaptioned test videos, simulate non-English audio by default
    fake_transcriber.set_error(
        "https://www.youtube.com/watch?v=vid_hindi", NonEnglishAudioError("hi", 0.99)
    )
    fake_transcriber.set_error(
        "https://www.youtube.com/watch?v=vid_no_subs", NonEnglishAudioError("unknown", 0.95)
    )
    service = TranscriptService(
        settings=settings,
        extractor=fake_extractor,
        transcriber=fake_transcriber,
    )

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_service_test",
            url="https://www.youtube.com/playlist?list=PL_service_test",
            title="Service Test Playlist",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_manual_en",
            title="Manual English Video",
            url="https://www.youtube.com/watch?v=vid_manual_en",
            position=0,
            status="DISCOVERED",
        )
        v2 = Video(
            playlist_id=pl.id,
            youtube_id="vid_auto_en",
            title="Auto English Video",
            url="https://www.youtube.com/watch?v=vid_auto_en",
            position=1,
            status="DISCOVERED",
        )
        v3 = Video(
            playlist_id=pl.id,
            youtube_id="vid_hindi",
            title="Hindi Video",
            url="https://www.youtube.com/watch?v=vid_hindi",
            position=2,
            status="DISCOVERED",
        )
        v4 = Video(
            playlist_id=pl.id,
            youtube_id="vid_no_subs",
            title="No Subtitles Video",
            url="https://www.youtube.com/watch?v=vid_no_subs",
            position=3,
            status="DISCOVERED",
        )
        v5 = Video(
            playlist_id=pl.id,
            youtube_id="vid_malformed",
            title="Malformed Video",
            url="https://www.youtube.com/watch?v=vid_malformed",
            position=4,
            status="DISCOVERED",
        )
        v6 = Video(
            playlist_id=pl.id,
            youtube_id="vid_deleted",
            title="Deleted Video",
            url="https://www.youtube.com/watch?v=vid_deleted",
            position=5,
            status="DISCOVERED",
        )
        session.add_all([v1, v2, v3, v4, v5, v6])
        session.commit()
        pl_id = pl.id

    return settings, service, fake_extractor, pl_id


# 1. Successful manual subtitle extraction
def test_successful_manual_subtitle_extraction(service_env):
    settings, service, extractor, _ = service_env
    url = "https://www.youtube.com/watch?v=vid_manual_en"
    extractor.set_response(
        url, SAMPLE_JSON3_ENGLISH, format_name="json3", language="en", source="manual"
    )

    with next(get_db(settings)) as session:
        video = session.scalars(select(Video).where(Video.youtube_id == "vid_manual_en")).first()
        summary = service.process_video(session, video)
        session.commit()

        assert summary.status == "TRANSCRIPT_READY"
        assert summary.source == "manual"
        assert summary.language == "en"
        assert summary.segment_count == 3
        assert Path(summary.artifact_path).exists()

        # Check Video status updated
        assert video.status == "TRANSCRIPT_READY"

        # Check ProcessingStage updated
        stage = session.scalars(
            select(ProcessingStage).where(ProcessingStage.video_id == video.id)
        ).first()
        assert stage is not None
        assert stage.status == "COMPLETED"
        assert stage.artifact_path is not None

        # Check Segments in DB
        segments = transcript_repository.get_by_video_id(session, video.id)
        assert len(segments) == 3
        assert segments[0].text == "Hello & welcome to the course."
        assert segments[0].start_seconds == 0.0
        assert segments[0].end_seconds == 2.5


# 2. Successful automatically generated subtitle extraction
def test_successful_auto_generated_subtitle_extraction(service_env):
    settings, service, extractor, _ = service_env
    url = "https://www.youtube.com/watch?v=vid_auto_en"
    extractor.set_response(
        url, SAMPLE_VTT_ENGLISH, format_name="vtt", language="en", source="generated"
    )

    with next(get_db(settings)) as session:
        video = session.scalars(select(Video).where(Video.youtube_id == "vid_auto_en")).first()
        summary = service.process_video(session, video)
        session.commit()

        assert summary.status == "TRANSCRIPT_READY"
        assert summary.source == "generated"
        assert summary.language == "en"
        assert summary.segment_count == 3
        assert video.status == "TRANSCRIPT_READY"

        segments = transcript_repository.get_by_video_id(session, video.id)
        assert len(segments) == 3
        assert segments[1].source == "generated"


# 3. Non-English-only subtitles available — must be treated as no captions
def test_non_english_only_available_marks_needs_transcription(service_env):
    """When only non-English (e.g. Hindi) captions exist, mark NEEDS_TRANSCRIPTION.

    The extractor is configured with English-only preferences; the fake extractor
    is told to raise CaptionsUnavailableError for the Hindi-only video — matching
    the real YtDlpSubtitleExtractor behaviour when no English track is found.
    The Whisper fallback detects non-English speech and marks NEEDS_TRANSCRIPTION.
    """
    settings, service, extractor, _ = service_env
    url = "https://www.youtube.com/watch?v=vid_hindi"
    extractor.set_error(url, CaptionsUnavailableError("No English subtitles found"))

    with next(get_db(settings)) as session:
        video = session.scalars(select(Video).where(Video.youtube_id == "vid_hindi")).first()
        summary = service.process_video(session, video)
        session.commit()

        assert summary.status == "NEEDS_TRANSCRIPTION"
        assert summary.error_category == "NON_ENGLISH_AUDIO"
        assert video.status == "NEEDS_TRANSCRIPTION"

        # No transcript segments should be stored
        assert transcript_repository.has_transcripts(session, video.id) is False


# 4. Missing subtitles
def test_missing_subtitles_marks_needs_transcription(service_env):
    settings, service, extractor, _ = service_env
    url = "https://www.youtube.com/watch?v=vid_no_subs"
    extractor.set_error(url, CaptionsUnavailableError("No subtitles found"))

    with next(get_db(settings)) as session:
        video = session.scalars(select(Video).where(Video.youtube_id == "vid_no_subs")).first()
        summary = service.process_video(session, video)
        session.commit()

        assert summary.status == "NEEDS_TRANSCRIPTION"
        assert summary.error_category == "NON_ENGLISH_AUDIO"

        # Video must be marked NEEDS_TRANSCRIPTION
        assert video.status == "NEEDS_TRANSCRIPTION"

        stage = session.scalars(
            select(ProcessingStage).where(ProcessingStage.video_id == video.id)
        ).first()
        assert stage.status == "SKIPPED"
        assert stage.error_category == "NON_ENGLISH_AUDIO"

        # Verify no transcript segments were added
        assert transcript_repository.has_transcripts(session, video.id) is False


# 5. Invalid or malformed subtitle data
def test_invalid_or_malformed_subtitle_data_handled(service_env):
    settings, service, extractor, _ = service_env
    url = "https://www.youtube.com/watch?v=vid_malformed"
    extractor.set_response(url, "malformed-not-valid-json", format_name="json3", language="en")

    with next(get_db(settings)) as session:
        video = session.scalars(select(Video).where(Video.youtube_id == "vid_malformed")).first()
        summary = service.process_video(session, video)
        session.commit()

        assert summary.status == "EXTRACTION_FAILED"
        assert summary.error_category == "MALFORMED_SUBTITLES"
        assert video.status == "EXTRACTION_FAILED"

        stage = session.scalars(
            select(ProcessingStage).where(ProcessingStage.video_id == video.id)
        ).first()
        assert stage.status == "FAILED"
        assert stage.error_category == "MALFORMED_SUBTITLES"


# 6. Unavailable or deleted video
def test_unavailable_or_deleted_video_marked_skipped(service_env):
    settings, service, extractor, _ = service_env
    url = "https://www.youtube.com/watch?v=vid_deleted"
    extractor.set_error(
        url, VideoUnavailableError("vid_deleted", "Video was removed by the uploader")
    )

    with next(get_db(settings)) as session:
        video = session.scalars(select(Video).where(Video.youtube_id == "vid_deleted")).first()
        summary = service.process_video(session, video)
        session.commit()

        assert summary.status == "SKIPPED_UNAVAILABLE"
        assert summary.error_category == "UNAVAILABLE"
        assert video.status == "SKIPPED_UNAVAILABLE"
        assert video.availability == "UNAVAILABLE"
        assert "removed by the uploader" in (video.discovery_error or "")

        stage = session.scalars(
            select(ProcessingStage).where(ProcessingStage.video_id == video.id)
        ).first()
        assert stage.status == "FAILED"
        assert stage.error_category == "UNAVAILABLE"


# 7. Duplicate processing prevention (idempotency)
def test_duplicate_processing_prevention(service_env):
    settings, service, extractor, _ = service_env
    url = "https://www.youtube.com/watch?v=vid_manual_en"
    extractor.set_response(
        url, SAMPLE_JSON3_ENGLISH, format_name="json3", language="en", source="manual"
    )

    with next(get_db(settings)) as session:
        video = session.scalars(select(Video).where(Video.youtube_id == "vid_manual_en")).first()
        # First extraction run
        res1 = service.process_video(session, video)
        session.commit()
        assert res1.status == "TRANSCRIPT_READY"
        initial_calls = extractor.call_count[url]

        # Second extraction run on same video
        res2 = service.process_video(session, video)
        session.commit()
        assert res2.status == "ALREADY_DONE"
        # Extractor should NOT have been called again!
        assert extractor.call_count[url] == initial_calls


# 8. Playlist batch processing does not abort on single video failure
def test_playlist_batch_processing_resilience(service_env):
    settings, service, extractor, pl_id = service_env

    # Configure some videos to succeed, some to fail, some unavailable
    extractor.set_response(
        "https://www.youtube.com/watch?v=vid_manual_en",
        SAMPLE_JSON3_ENGLISH,
        "json3",
        "en",
        "manual",
    )
    extractor.set_response(
        "https://www.youtube.com/watch?v=vid_auto_en", SAMPLE_VTT_ENGLISH, "vtt", "en", "generated"
    )
    extractor.set_error(
        "https://www.youtube.com/watch?v=vid_no_subs", CaptionsUnavailableError("No captions")
    )
    extractor.set_error(
        "https://www.youtube.com/watch?v=vid_deleted",
        VideoUnavailableError("vid_deleted", "Deleted"),
    )
    extractor.set_error(
        "https://www.youtube.com/watch?v=vid_malformed",
        TranscriptExtractionError("Network timeout"),
    )

    with next(get_db(settings)) as session:
        result = service.extract_for_playlist(session, pl_id)
        assert result.transcripts_ready >= 2
        assert result.needs_transcription >= 1
        assert result.skipped_unavailable >= 1
        assert result.failed >= 1


# 9. Idempotent transcript persistence — re-processing does not create duplicates
def test_idempotent_transcript_persistence(service_env):
    settings, service, extractor, _ = service_env
    url = "https://www.youtube.com/watch?v=vid_manual_en"
    extractor.set_response(
        url, SAMPLE_JSON3_ENGLISH, format_name="json3", language="en", source="manual"
    )

    with next(get_db(settings)) as session:
        video = session.scalars(select(Video).where(Video.youtube_id == "vid_manual_en")).first()
        # First run
        service.process_video(session, video)
        session.commit()
        count_after_first = len(transcript_repository.get_by_video_id(session, video.id))

        # Reset status so it would normally re-process (simulate manual override)
        video.status = "DISCOVERED"
        session.flush()

        # Second run — service must detect existing segments and skip extraction
        res2 = service.process_video(session, video)
        session.commit()

        count_after_second = len(transcript_repository.get_by_video_id(session, video.id))

    # Segment count must not have doubled
    assert count_after_first == 3
    assert count_after_second == count_after_first
    assert res2.status in ("TRANSCRIPT_READY", "ALREADY_DONE")


# 10. HTTP 429 handling — service records extraction failure, not unavailability
def test_http_429_handling_in_service(service_env):
    settings, service, extractor, _ = service_env
    url = "https://www.youtube.com/watch?v=vid_malformed"
    extractor.set_error(url, TranscriptExtractionError("HTTP 429: Too Many Requests"))

    with next(get_db(settings)) as session:
        video = session.scalars(select(Video).where(Video.youtube_id == "vid_malformed")).first()
        summary = service.process_video(session, video)
        session.commit()

        # Must be recorded as a failed extraction, NOT as unavailable
        assert summary.status == "EXTRACTION_FAILED"
        assert video.status == "EXTRACTION_FAILED"
        # Video availability should NOT be set to UNAVAILABLE
        assert (video.availability or "") != "UNAVAILABLE"
