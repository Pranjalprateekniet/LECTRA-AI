"""Unit tests for Phase 4: 75-second chunking and rolling caption deduplication."""

import uuid

import pytest
from lectra_core.chunking.deduplicator import deduplicate_rolling_captions
from lectra_core.chunking.service import CHUNK_UUID_NAMESPACE, ChunkingService
from lectra_core.config import Settings
from lectra_core.db.models import Playlist, Video, VideoChunk
from lectra_core.db.session import get_engine, init_db
from lectra_core.repositories import transcript_repository
from lectra_core.transcript.models import TranscriptSegmentData
from lectra_core.transcript.ytdlp_extractor import select_best_track
from sqlalchemy import select
from sqlalchemy.orm import Session


@pytest.fixture
def chunking_db(tmp_path):
    """In-memory or temp SQLite DB initialized with tables."""
    db_file = tmp_path / "test_chunking.db"
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
        playlist = Playlist(
            id="test_pl",
            youtube_id="PL_test_123",
            url="https://youtube.com/playlist?list=PL_test_123",
            title="Test Playlist",
            status="DISCOVERY_COMPLETED",
        )
        session.add(playlist)
        session.commit()
        yield session, settings


# ==============================================================================
# Phase B: Rolling Caption Deduplication Tests
# ==============================================================================

def test_rolling_caption_deduplication_removes_repeated_cues():
    """Verify that adjacent cues with overlapping timestamps strip duplicates."""
    cues = [
        {"segment_index": 0, "start_seconds": 0.0, "end_seconds": 4.0, "text": "welcome back to"},
        {"segment_index": 1, "start_seconds": 2.5, "end_seconds": 6.5, "text": "back to channel"},
    ]
    cleaned = deduplicate_rolling_captions(cues)
    assert len(cleaned) == 2
    assert cleaned[0][1] == "welcome back to"
    assert cleaned[1][1] == "channel"  # "back to" was stripped because of overlap


def test_rolling_caption_drops_full_duplicate_cue():
    """Verify that a cue completely covered by the previous suffix is omitted."""
    cues = [
        {"segment_index": 0, "start_seconds": 10.0, "end_seconds": 15.0, "text": "take it now"},
        {"segment_index": 1, "start_seconds": 13.0, "end_seconds": 16.0, "text": "now"},
        {"segment_index": 2, "start_seconds": 16.0, "end_seconds": 20.0, "text": "a valid option"},
    ]
    cleaned = deduplicate_rolling_captions(cues)
    assert len(cleaned) == 2
    assert cleaned[0][1] == "take it now"
    assert cleaned[1][1] == "a valid option"


def test_preserves_legitimate_speech_repetition():
    """Verify that genuinely repeated speech is preserved when not a sliding-window artifact."""
    # 1. Inner-cue repetition like "please please please"
    cue_inner = [
        {"segment_index": 0, "start_seconds": 0.0, "end_seconds": 5.0, "text": "please please"},
    ]
    res_inner = deduplicate_rolling_captions(cue_inner)
    assert res_inner[0][1] == "please please"

    # 2. Repeated phrase across non-overlapping cues
    cue_spaced = [
        {"segment_index": 0, "start_seconds": 0.0, "end_seconds": 3.0, "text": "repeat this"},
        {"segment_index": 1, "start_seconds": 3.5, "end_seconds": 6.0, "text": "repeat this"},
    ]
    res_spaced = deduplicate_rolling_captions(cue_spaced)
    assert len(res_spaced) == 2
    assert res_spaced[0][1] == "repeat this"
    assert res_spaced[1][1] == "repeat this"  # No time overlap => preserved


# ==============================================================================
# Phase A & D: 75-Second Chunking Tests
# ==============================================================================

def test_75_second_chunk_boundaries_and_sentence_awareness(chunking_db):
    """Verify chunking targets ~75s and prefers sentence-ending boundaries."""
    session, settings = chunking_db

    video = Video(
        playlist_id="test_pl",
        youtube_id="vid_75s_test",
        title="Test 75s Video",
        url="https://youtube.com/watch?v=vid_75s_test",
        status="TRANSCRIPT_READY",
    )
    session.add(video)
    session.flush()

    segs = []
    for i in range(30):
        start = i * 5.0
        end = (i + 1) * 5.0
        text = f"Segment sentence {i}." if i in (13, 29) else f"segment {i}"
        segs.append(
            TranscriptSegmentData(
                segment_index=i,
                start_seconds=start,
                end_seconds=end,
                duration_seconds=5.0,
                text=text,
                language="en",
                source="whisper",
            )
        )
    transcript_repository.save_segments(session, video.id, segs)
    session.commit()

    service = ChunkingService(
        settings=settings,
        target_duration=75.0,
        min_duration=60.0,
        max_duration=90.0,
    )
    chunks = service.chunk_video(session, video)

    assert len(chunks) == 2
    # Chunk 0 should break at segment 13 (ends at 70s) due to sentence boundary
    c0 = chunks[0]
    assert c0.chunk_index == 0
    assert c0.start_seconds == 0.0
    assert c0.end_seconds == 70.0
    assert c0.duration_seconds == 70.0
    assert c0.source_segment_start_index == 0
    assert c0.source_segment_end_index == 13
    assert c0.text.endswith("Segment sentence 13.")

    # Chunk 1 covers the rest (70.0s to 150.0s = 80s)
    c1 = chunks[1]
    assert c1.chunk_index == 1
    assert c1.start_seconds == 70.0
    assert c1.end_seconds == 150.0
    assert c1.duration_seconds == 80.0
    assert c1.source_segment_start_index == 14
    assert c1.source_segment_end_index == 29


def test_short_final_chunk(chunking_db):
    """Verify that a video with trailing duration produces a valid short final chunk."""
    session, settings = chunking_db

    video = Video(
        playlist_id="test_pl",
        youtube_id="vid_short_final",
        title="Short Final Test",
        url="https://youtube.com/watch?v=vid_short_final",
        status="TRANSCRIPT_READY",
    )
    session.add(video)
    session.flush()

    # 22 segments of 5s each = 110s total
    # Chunk 0: 0.0s to 75.0s (15 segs)
    # Chunk 1 (short final): 75.0s to 110.0s (7 segs, 35s duration)
    segs = [
        TranscriptSegmentData(
            segment_index=i,
            start_seconds=i * 5.0,
            end_seconds=(i + 1) * 5.0,
            duration_seconds=5.0,
            text=f"word {i}",
            language="en",
            source="whisper",
        )
        for i in range(22)
    ]
    transcript_repository.save_segments(session, video.id, segs)
    session.commit()

    service = ChunkingService(settings=settings, target_duration=75.0, min_duration=60.0)
    chunks = service.chunk_video(session, video)

    assert len(chunks) == 2
    assert chunks[0].duration_seconds == 90.0
    assert chunks[1].duration_seconds == 20.0  # Valid short final chunk (< min_duration)
    assert chunks[1].chunk_index == 1


def test_deterministic_chunk_ids(chunking_db):
    """Verify that chunk IDs are generated deterministically using UUID5."""
    session, settings = chunking_db

    video_id = str(uuid.uuid4())
    expected_id_0 = str(uuid.uuid5(CHUNK_UUID_NAMESPACE, f"{video_id}:0"))
    expected_id_1 = str(uuid.uuid5(CHUNK_UUID_NAMESPACE, f"{video_id}:1"))

    video = Video(
        id=video_id,
        playlist_id="test_pl",
        youtube_id="vid_deterministic",
        title="Deterministic Test",
        url="https://youtube.com/watch?v=vid_deterministic",
        status="TRANSCRIPT_READY",
    )
    session.add(video)
    session.flush()

    segs = [
        TranscriptSegmentData(
            segment_index=0,
            start_seconds=0.0,
            end_seconds=75.0,
            duration_seconds=75.0,
            text="First chunk text.",
            language="en",
            source="whisper",
        ),
        TranscriptSegmentData(
            segment_index=1,
            start_seconds=75.0,
            end_seconds=150.0,
            duration_seconds=75.0,
            text="Second chunk text.",
            language="en",
            source="whisper",
        ),
    ]
    transcript_repository.save_segments(session, video.id, segs)
    session.commit()

    service = ChunkingService(settings=settings)
    chunks = service.chunk_video(session, video)

    assert chunks[0].id == expected_id_0
    assert chunks[1].id == expected_id_1


def test_idempotent_regeneration(chunking_db):
    """Verify that re-running chunking updates/replaces records without creating duplicates."""
    session, settings = chunking_db

    video = Video(
        playlist_id="test_pl",
        youtube_id="vid_idempotent",
        title="Idempotent Test",
        url="https://youtube.com/watch?v=vid_idempotent",
        status="TRANSCRIPT_READY",
    )
    session.add(video)
    session.flush()

    segs = [
        TranscriptSegmentData(
            segment_index=0,
            start_seconds=0.0,
            end_seconds=75.0,
            duration_seconds=75.0,
            text="Sample chunk text.",
            language="en",
            source="whisper",
        ),
    ]
    transcript_repository.save_segments(session, video.id, segs)
    session.commit()

    service = ChunkingService(settings=settings)
    # Run 1
    chunks_run1 = service.chunk_video(session, video)
    assert len(chunks_run1) == 1

    # Run 2
    chunks_run2 = service.chunk_video(session, video)
    assert len(chunks_run2) == 1

    # Total in DB must remain exactly 1
    total_in_db = session.scalars(
        select(VideoChunk).where(VideoChunk.video_id == video.id)
    ).all()
    assert len(total_in_db) == 1
    assert total_in_db[0].id == chunks_run1[0].id


# ==============================================================================
# Phase C: Extraction Priority & Multilingual Whisper Fallback Tests
# ==============================================================================

def test_subtitle_selection_priority():
    """Verify subtitle track priority: manual en > auto en > non-en > None."""
    # 1. Manual English preferred over auto English
    subtitles = {"en": [{"ext": "json3", "url": "https://example.com/en_manual"}]}
    auto = {"en": [{"ext": "json3", "url": "https://example.com/en_auto"}]}
    chosen = select_best_track(subtitles, auto, preferred_languages=["en"], prefer_manual=True)
    assert chosen is not None
    assert chosen[2] == "manual"

    # 2. Auto English selected if manual English is unavailable
    subtitles_hi = {"hi": [{"ext": "json3", "url": "https://example.com/hi_manual"}]}
    chosen_auto = select_best_track(
        subtitles_hi, auto, preferred_languages=["en"], prefer_manual=True
    )
    assert chosen_auto is not None
    assert chosen_auto[2] == "generated"
    assert chosen_auto[1] == "en"

    # 3. Non-English subtitles selected as translation input if no English subtitles exist
    chosen_non_en = select_best_track(
        subtitles_hi,
        {},
        preferred_languages=["en"],
        prefer_manual=True,
        allow_non_english=True,
    )
    assert chosen_non_en is not None
    assert chosen_non_en[1] == "hi"


def test_multilingual_whisper_translation_mode():
    """Verify multilingual model mode detects translation configuration."""
    settings = Settings(whisper_model_name="small", whisper_device="cpu")
    assert not settings.whisper_model_name.endswith(".en")
