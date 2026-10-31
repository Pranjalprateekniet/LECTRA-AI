"""Real yt-dlp integration test using the Striver Greedy Algorithms playlist.

Playlist: https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ (5 videos)
"""

import logging

import pytest
from lectra_core.config import Settings
from lectra_core.db.models import Video
from lectra_core.db.session import get_db, get_engine, init_db
from lectra_core.discovery.service import DiscoveryService
from lectra_core.discovery.ytdlp_client import YtDlpProvider
from lectra_core.logging import get_logger
from lectra_core.repositories import transcript_repository
from lectra_core.transcript.service import TranscriptService
from lectra_core.transcript.ytdlp_extractor import YtDlpSubtitleExtractor
from sqlalchemy import select

GREEDY_PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
MAX_TEST_VIDEOS = 5
SOCKET_TIMEOUT_SECONDS = 20

logger = get_logger("lectra.test.integration")


@pytest.fixture
def integration_env(tmp_path):
    """Isolated environment with temporary SQLite DB and artifact store."""
    db_file = tmp_path / "greedy_integration.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file}",
        data_dir=tmp_path,
        artifacts_dir=tmp_path / "artifacts",
        temp_audio_dir=tmp_path / "temp_audio",
        model_cache_dir=tmp_path / "models",
        discovery_socket_timeout_seconds=SOCKET_TIMEOUT_SECONDS,
        subtitle_socket_timeout_seconds=SOCKET_TIMEOUT_SECONDS,
        subtitle_languages=["en"],
        subtitle_prefer_manual=True,
        whisper_model_name="tiny.en",
        whisper_device="auto",
        whisper_compute_type="auto",
        whisper_beam_size=3,
    )
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)
    return settings


@pytest.mark.integration
def test_real_greedy_playlist_transcript_extraction(integration_env, caplog):
    """Verify real subtitle extraction for the 5-video Greedy Algorithms playlist.

    - Limits processing to a maximum of 5 videos.
    - Tests actual English subtitle extraction only.
    - Preserves timestamp and segment persistence checks in SQLite.
    - Enforces bounded network timeouts so execution cannot hang.
    """
    caplog.set_level(logging.INFO)
    settings = integration_env

    # 1. Discover the playlist using real yt-dlp (bounded to max 5 items and 20s socket timeout)
    print(f"\n--- Discovering playlist: {GREEDY_PLAYLIST_URL} ---", flush=True)
    disc_provider = YtDlpProvider(
        options={
            "socket_timeout": SOCKET_TIMEOUT_SECONDS,
            "playlistend": MAX_TEST_VIDEOS,
        }
    )
    disc_service = DiscoveryService(provider=disc_provider)

    with next(get_db(settings)) as session:
        disc_result = disc_service.discover(session, GREEDY_PLAYLIST_URL)
        assert disc_result.distinct_videos > 0
        total_discovered = min(disc_result.distinct_videos, MAX_TEST_VIDEOS)
        print(
            f"Discovered {disc_result.distinct_videos} videos (testing up to {total_discovered})",
            flush=True,
        )

    # 2. Extract English subtitles for discovered videos (capped at MAX_TEST_VIDEOS)
    extractor = YtDlpSubtitleExtractor(settings=settings)
    transcript_service = TranscriptService(settings=settings, extractor=extractor)

    successful_transcripts = 0

    with next(get_db(settings)) as session:
        videos = session.scalars(
            select(Video)
            .where(Video.status == "DISCOVERED")
            .order_by(Video.position.asc())
            .limit(MAX_TEST_VIDEOS)
        ).all()

        assert len(videos) > 0, "No discovered videos available to test"
        total_to_process = len(videos)

        for idx, video in enumerate(videos, start=1):
            progress_msg = (
                f"[{idx}/{total_to_process}] Processing video: {video.title} "
                f"(ID: {video.youtube_id})"
            )
            print(f"\n{progress_msg}", flush=True)
            logger.info(progress_msg)

            summary = transcript_service.process_video(session, video)
            session.commit()

            result_msg = (
                f"[{idx}/{total_to_process}] Finished {video.youtube_id}: "
                f"status={summary.status}, lang={summary.language}, "
                f"source={summary.source}, segments={summary.segment_count}"
            )
            print(result_msg, flush=True)
            logger.info(result_msg)

            # Each video must either succeed with English transcripts or be flagged for Whisper
            assert summary.status in ("TRANSCRIPT_READY", "NEEDS_TRANSCRIPTION")

            if summary.status == "TRANSCRIPT_READY":
                successful_transcripts += 1
                # Must be English
                assert summary.language is not None
                assert summary.language.lower().startswith("en"), (
                    f"Expected English transcript, got {summary.language}"
                )
                assert summary.segment_count > 0

                # Validate persistence in SQLite
                segments = transcript_repository.get_by_video_id(session, video.id)
                assert len(segments) == summary.segment_count

                # Verify timestamp ordering and validity
                first_seg = segments[0]
                assert first_seg.start_seconds >= 0.0
                assert first_seg.end_seconds >= first_seg.start_seconds
                assert len(first_seg.text.strip()) > 0
                assert first_seg.language.lower().startswith("en")

                # Verify monotonic ordering
                for i in range(1, len(segments)):
                    assert segments[i].start_seconds >= segments[i - 1].start_seconds
                    assert segments[i].segment_index == i

    print(
        f"\n--- Integration test completed: "
        f"{successful_transcripts}/{total_to_process} videos extracted transcripts ---",
        flush=True,
    )
    assert successful_transcripts > 0, "Expected at least one video to have English transcripts"
