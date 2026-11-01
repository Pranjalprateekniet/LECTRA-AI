"""Unit tests for Captions-First Ingestion, Argos Translation, and Chunking."""

from unittest.mock import MagicMock

import pytest
from lectra_core.chunking.service import ChunkingService
from lectra_core.config import Settings
from lectra_core.db.models import Playlist, ProcessingStage, Video
from lectra_core.db.session import get_engine, init_db
from lectra_core.repositories import transcript_repository
from lectra_core.transcript.models import (
    CaptionsUnavailableError,
    TranscriptSegmentData,
)
from lectra_core.transcript.service import TranscriptService
from lectra_core.transcript.ytdlp_extractor import select_best_track
from lectra_core.translation.service import TranslationService, UnsupportedLanguageError
from sqlalchemy import select
from sqlalchemy.orm import Session


@pytest.fixture
def captions_first_db(tmp_path):
    """Set up temporary database for captions-first pipeline testing."""
    db_file = tmp_path / "test_captions_first.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file}",
        data_dir=tmp_path,
        artifacts_dir=tmp_path / "artifacts",
        temp_audio_dir=tmp_path / "temp_audio",
        model_cache_dir=tmp_path / "models",
    )
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)

    with Session(engine) as session:
        pl = Playlist(
            id="test_pl_cf",
            youtube_id="PL_CF_123",
            url="https://youtube.com/playlist?list=PL_CF_123",
            title="Captions First Playlist",
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.commit()
        yield session, settings


def test_caption_selection_priority():
    """Verify track priority: auto EN > manual EN > Hindi > other languages."""
    # 1. Both auto and manual English available -> prefer auto English as primary
    subtitles = {"en": [{"ext": "json3", "url": "https://example.com/en_manual"}]}
    auto = {"en": [{"ext": "json3", "url": "https://example.com/en_auto"}]}
    chosen = select_best_track(subtitles, auto)
    assert chosen is not None
    assert chosen[1] == "en"
    assert chosen[2] == "generated"

    # 2. Only manual English available -> select manual English
    chosen_manual = select_best_track(subtitles, {})
    assert chosen_manual is not None
    assert chosen_manual[1] == "en"
    assert chosen_manual[2] == "manual"

    # 3. No English captions, but Hindi captions exist -> select Hindi
    subtitles_hi = {"hi": [{"ext": "json3", "url": "https://example.com/hi_manual"}]}
    chosen_hi = select_best_track(subtitles_hi, {})
    assert chosen_hi is not None
    assert chosen_hi[1] == "hi"
    assert chosen_hi[2] == "manual"

    # 4. No captions at all -> returns None
    assert select_best_track({}, {}) is None


def test_argos_translation_service_offline_hindi_to_english():
    """Verify offline translation of Hindi segments into English while preserving timestamps."""
    service = TranslationService()

    assert service.is_language_supported("hi") is True
    assert service.is_language_supported("en") is True
    assert service.is_language_supported("xx") is False

    hindi_segments = [
        TranscriptSegmentData(
            segment_index=0,
            start_seconds=0.0,
            end_seconds=4.5,
            duration_seconds=4.5,
            text="नमस्ते दोस्तों",
            language="hi",
            source="generated",
        ),
        TranscriptSegmentData(
            segment_index=1,
            start_seconds=4.5,
            end_seconds=9.0,
            duration_seconds=4.5,
            text="यह एक परीक्षण है",
            language="hi",
            source="generated",
        ),
    ]

    translated = service.translate_segments(hindi_segments, source_lang="hi")
    assert len(translated) == 2

    # Preserves order and segment index
    assert translated[0].segment_index == 0
    assert translated[1].segment_index == 1

    # Preserves exact timestamps
    assert translated[0].start_seconds == 0.0
    assert translated[0].end_seconds == 4.5
    assert translated[1].start_seconds == 4.5
    assert translated[1].end_seconds == 9.0

    # Translates text into English
    assert translated[0].language == "en"
    assert "Hello" in translated[0].text or "hello" in translated[0].text.lower()
    assert translated[1].language == "en"
    assert "test" in translated[1].text.lower()


def test_unsupported_language_raises_error():
    """Verify unsupported languages raise error and are never indexed untranslated."""
    service = TranslationService()

    segments = [
        TranscriptSegmentData(
            segment_index=0,
            start_seconds=0.0,
            end_seconds=3.0,
            duration_seconds=3.0,
            text="Texte en français non supporté",
            language="fr",
            source="manual",
        )
    ]

    with pytest.raises(UnsupportedLanguageError):
        service.translate_segments(segments, source_lang="fr")


def test_transcript_service_translates_hindi_captions(captions_first_db):
    """Verify TranscriptService extracts Hindi, translates, and persists English segments."""
    session, settings = captions_first_db

    video = Video(
        playlist_id="test_pl_cf",
        youtube_id="vid_hindi_lecture",
        title="Greedy Algorithms in Hindi",
        url="https://www.youtube.com/watch?v=vid_hindi_lecture",
        status="DISCOVERED",
    )
    session.add(video)
    session.commit()

    # Mock extractor returning Hindi captions
    raw_content = {
        "events": [
            {
                "tStartMs": 0,
                "dDurationMs": 4000,
                "segs": [{"utf8": "नमस्ते दोस्तों"}],
            },
            {
                "tStartMs": 4000,
                "dDurationMs": 4000,
                "segs": [{"utf8": "आज हम ग्रीडी एल्गोरिदम सीखेंगे"}],
            },
        ]
    }

    mock_extractor = MagicMock()
    from lectra_core.transcript.ytdlp_extractor import RawSubtitleTrack

    mock_extractor.extract_subtitles.return_value = RawSubtitleTrack(
        content=raw_content,
        format_name="json3",
        language="hi",
        source="generated",
    )

    service = TranscriptService(settings=settings, extractor=mock_extractor)
    summary = service.process_video(session, video)

    assert summary.status == "TRANSCRIPT_READY"
    assert summary.language == "en"
    assert summary.segment_count == 2

    # Segments saved in SQLite must be English
    saved_segments = transcript_repository.get_by_video_id(session, video.id)
    assert len(saved_segments) == 2
    assert saved_segments[0].language == "en"
    assert saved_segments[0].start_seconds == 0.0
    assert saved_segments[0].end_seconds == 4.0

    # Translation stage recorded
    stage = session.scalars(
        select(ProcessingStage).where(
            ProcessingStage.video_id == video.id,
            ProcessingStage.stage_name == "TRANSLATION",
        )
    ).first()
    assert stage is not None
    assert stage.status == "COMPLETED"


def test_transcript_service_captions_unavailable_no_whisper(captions_first_db):
    """Verify missing captions marks NEEDS_TRANSCRIPTION and Whisper is NOT run."""
    session, settings = captions_first_db

    video = Video(
        playlist_id="test_pl_cf",
        youtube_id="vid_no_captions_at_all",
        title="Silent Video Without Captions",
        url="https://www.youtube.com/watch?v=vid_no_captions_at_all",
        status="DISCOVERED",
    )
    session.add(video)
    session.commit()

    mock_extractor = MagicMock()
    mock_extractor.extract_subtitles.side_effect = CaptionsUnavailableError("No captions found")

    # In normal ingestion, transcriber is None
    service = TranscriptService(settings=settings, extractor=mock_extractor, transcriber=None)
    summary = service.process_video(session, video)

    assert summary.status == "NEEDS_TRANSCRIPTION"
    assert summary.error_category == "CAPTIONS_UNAVAILABLE"
    assert video.status == "NEEDS_TRANSCRIPTION"
    assert video.discovery_error == "CAPTIONS_UNAVAILABLE"

    # Stage is SKIPPED with CAPTIONS_UNAVAILABLE
    stage = session.scalars(
        select(ProcessingStage).where(
            ProcessingStage.video_id == video.id,
            ProcessingStage.stage_name == "TRANSCRIPT_ACQUISITION",
        )
    ).first()
    assert stage is not None
    assert stage.status == "SKIPPED"
    assert stage.error_category == "CAPTIONS_UNAVAILABLE"


def test_chunking_fixed_75s_5s_overlap(captions_first_db):
    """Verify chunking adheres strictly to fixed 75s duration, 5s overlap specification."""
    session, settings = captions_first_db

    video = Video(
        playlist_id="test_pl_cf",
        youtube_id="vid_chunk_spec",
        title="Chunk Spec Verification Video",
        url="https://www.youtube.com/watch?v=vid_chunk_spec",
        status="TRANSCRIPT_READY",
    )
    session.add(video)
    session.commit()

    # Video with 210 seconds of speech (42 segments of 5s each)
    segs = [
        TranscriptSegmentData(
            segment_index=i,
            start_seconds=i * 5.0,
            end_seconds=(i + 1) * 5.0,
            duration_seconds=5.0,
            text=f"speech unit {i}",
            language="en",
            source="generated",
        )
        for i in range(42)
    ]
    transcript_repository.save_segments(session, video.id, segs)
    session.commit()

    service = ChunkingService(settings=settings)
    chunks = service.chunk_video(session, video)

    # 210s total:
    # Chunk 1 (0): 0s to 75s
    # Chunk 2 (1): 70s to 145s
    # Chunk 3 (2): 140s to 210s (covered up to video end)
    assert len(chunks) == 3

    assert chunks[0].chunk_index == 0
    assert chunks[0].start_seconds == 0.0
    assert chunks[0].end_seconds == 75.0
    assert chunks[0].duration_seconds == 75.0

    assert chunks[1].chunk_index == 1
    assert chunks[1].start_seconds == 70.0
    assert chunks[1].end_seconds == 145.0
    assert chunks[1].duration_seconds == 75.0

    assert chunks[2].chunk_index == 2
    assert chunks[2].start_seconds == 140.0
    assert chunks[2].end_seconds == 210.0
    assert chunks[2].duration_seconds == 70.0
