"""Controlled transcript extraction script for five specific YouTube videos.

Target videos:
- II6ziNnub1Q: N meetings In One Room | Greedy Algorithm
- dxVcMDI7vyI: Minimum Platforms | Greedy Algorithms
- LjPx4wQaRIs: Job Sequencing Problem | Greedy Algorithms
- F_DDzYnxO14: Fractional Knapsack | Greedy Algorithms
- mVg9CfJvayM: Minimum Coins | Greedy Algorithms

Pipeline:
1. Reuses existing video records from `data/revision_rag.db`.
2. Runs caption-first English extraction; falls back to local Whisper speech-to-text.
3. Persist transcript segments to SQLite (`transcript_segments`) and JSON artifacts.
4. Updates `processing_stages` and `videos` status idempotently.
5. Ignores all other videos in the database.
"""

import sys
from pathlib import Path

# Ensure core and backend packages are on path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "core" / "src"))
sys.path.insert(0, str(repo_root / "backend" / "src"))

from lectra_core.config import get_settings  # noqa: E402
from lectra_core.db.models import ProcessingStage, TranscriptSegment, Video  # noqa: E402
from lectra_core.db.session import get_db  # noqa: E402
from lectra_core.logging import setup_logging  # noqa: E402
from lectra_core.transcript.service import TranscriptService  # noqa: E402
from lectra_core.transcript.whisper_transcriber import WhisperModelManager  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

TARGET_YOUTUBE_IDS = [
    "II6ziNnub1Q",
    "dxVcMDI7vyI",
    "LjPx4wQaRIs",
    "F_DDzYnxO14",
    "mVg9CfJvayM",
]


def main() -> int:
    settings = get_settings()
    setup_logging(settings)

    print("=" * 70)
    print("Controlled Transcript Extraction for 5 Target Videos")
    print(f"Database: {settings.database_url}")
    print(f"Artifacts: {settings.artifacts_dir}")
    print(f"Whisper Model: {settings.whisper_model_name} (Device: {settings.whisper_device})")
    print("=" * 70)

    service = TranscriptService(settings=settings)

    with next(get_db(settings)) as session:
        # 1. Fetch exactly the 5 target videos by youtube_id
        stmt = select(Video).where(Video.youtube_id.in_(TARGET_YOUTUBE_IDS))
        found_videos = {v.youtube_id: v for v in session.scalars(stmt).all()}

        missing = [y_id for y_id in TARGET_YOUTUBE_IDS if y_id not in found_videos]
        if missing:
            print(f"ERROR: Missing video records in database: {missing}", file=sys.stderr)
            return 1

        # Preserve the specified order
        target_videos = [found_videos[y_id] for y_id in TARGET_YOUTUBE_IDS]

        print("\nFound all 5 target records in database:")
        for idx, vid in enumerate(target_videos, 1):
            print(
                f"  [{idx}/5] DB ID: {vid.id} | YouTube: {vid.youtube_id} | "
                f"Status: {vid.status} | Title: {vid.title[:40]}"
            )

        # 2. Process each video idempotently
        print("\nStarting transcript extraction...\n")
        results = []
        try:
            for idx, video in enumerate(target_videos, 1):
                print(
                    f"[{idx}/{len(target_videos)}] Processing: "
                    f"{video.youtube_id} - '{video.title[:45]}'"
                )
                summary = service.process_video(session, video)
                session.commit()
                results.append((video, summary))

                print(
                    f"       -> Status: {summary.status} | Source: {summary.source} | "
                    f"Language: {summary.language} | Segments: {summary.segment_count}"
                )
                if summary.artifact_path:
                    print(f"       -> Artifact: {summary.artifact_path}")
                if summary.error_detail:
                    print(f"       -> Note/Error: {summary.error_detail}")
                print()
        finally:
            # Unload Whisper model to free memory/VRAM
            WhisperModelManager.get_instance().unload_model()

        # 3. Final verification of records in database
        print("\n" + "=" * 70)
        print("Final Verification Summary from SQLite")
        print("=" * 70)
        all_ok = True
        for vid, summary in results:
            session.refresh(vid)
            total_segs = session.scalar(
                select(func.count(TranscriptSegment.id)).where(
                    TranscriptSegment.video_id == vid.id
                )
            ) or 0
            stage = session.scalars(
                select(ProcessingStage).where(
                    ProcessingStage.video_id == vid.id,
                    ProcessingStage.stage_name == "TRANSCRIPT_ACQUISITION",
                )
            ).first()

            stage_status = stage.status if stage else "NONE"
            print(
                f"- {vid.youtube_id} (DB ID: {vid.id}):\n"
                f"    Video Status:   {vid.status}\n"
                f"    Stage Status:   {stage_status}\n"
                f"    Segments in DB: {total_segs}\n"
                f"    Source:         {summary.source}\n"
            )
            if vid.status != "TRANSCRIPT_READY" or total_segs == 0:
                all_ok = False

        if all_ok:
            print("SUCCESS: All 5 videos have completed transcript extraction and persistence.")
            return 0
        else:
            print("WARNING: One or more videos did not complete as TRANSCRIPT_READY.")
            return 1


if __name__ == "__main__":
    sys.exit(main())
