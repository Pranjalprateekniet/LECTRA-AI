"""Targeted chunk generation script for the five Greedy Algorithm videos.

Scanned IDs:
- II6ziNnub1Q: N meetings In One Room | Greedy Algorithm
- dxVcMDI7vyI: Minimum Platforms | Greedy Algorithms
- LjPx4wQaRIs: Job Sequencing Problem | Greedy Algorithms
- F_DDzYnxO14: Fractional Knapsack | Greedy Algorithms
- mVg9CfJvayM: Minimum Coins | Greedy Algorithms

This script operates directly on `data/revision_rag.db` using the existing
`ChunkingService`. It is strictly scoped to these 5 records.
"""

import sys
from pathlib import Path

# Ensure core and backend packages are on path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "core" / "src"))
sys.path.insert(0, str(repo_root / "backend" / "src"))

from lectra_core.chunking.service import ChunkingService  # noqa: E402
from lectra_core.config import get_settings  # noqa: E402
from lectra_core.db.models import ProcessingStage, Video, VideoChunk  # noqa: E402
from lectra_core.db.session import get_db  # noqa: E402
from lectra_core.logging import setup_logging  # noqa: E402
from sqlalchemy import select  # noqa: E402

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
    print("Controlled 75-Second Chunk Generation for 5 Greedy Videos")
    print(f"Database: {settings.database_url}")
    print("=" * 70)

    service = ChunkingService(settings=settings)

    with next(get_db(settings)) as session:
        # 1. Fetch exactly the 5 target videos
        stmt = select(Video).where(Video.youtube_id.in_(TARGET_YOUTUBE_IDS))
        found_videos = {v.youtube_id: v for v in session.scalars(stmt).all()}

        missing = [y_id for y_id in TARGET_YOUTUBE_IDS if y_id not in found_videos]
        if missing:
            print(f"ERROR: Missing video records in database: {missing}", file=sys.stderr)
            return 1

        target_videos = [found_videos[y_id] for y_id in TARGET_YOUTUBE_IDS]

        print("\nTarget videos found in database:")
        for idx, vid in enumerate(target_videos, 1):
            print(
                f"  [{idx}/5] DB ID: {vid.id} | YouTube: {vid.youtube_id} | "
                f"Status: {vid.status} | Title: {vid.title[:40]}"
            )

        print("\nStarting chunk generation...\n")
        results = []

        for idx, video in enumerate(target_videos, 1):
            print(f"[{idx}/5] Chunking: {video.youtube_id} - '{video.title[:45]}'")
            chunks = service.chunk_video(session, video)
            session.commit()
            results.append((video, chunks))

            durations = [c.duration_seconds for c in chunks]
            min_dur = min(durations) if durations else 0.0
            max_dur = max(durations) if durations else 0.0
            avg_dur = (sum(durations) / len(durations)) if durations else 0.0
            total_tokens = sum(c.token_count for c in chunks)

            print(
                f"       -> Generated {len(chunks)} chunks | Total Tokens: {total_tokens} | "
                f"Durations: min={min_dur:.2f}s, max={max_dur:.2f}s, avg={avg_dur:.2f}s"
            )
            print()

        # Final verification summary
        print("=" * 70)
        print("Final Chunking Verification Summary")
        print("=" * 70)
        for vid, chunks in results:
            session.refresh(vid)
            stage = session.scalars(
                select(ProcessingStage).where(
                    ProcessingStage.video_id == vid.id,
                    ProcessingStage.stage_name == "CHUNKING",
                )
            ).first()
            stage_status = stage.status if stage else "NONE"
            db_chunks = session.scalars(
                select(VideoChunk).where(VideoChunk.video_id == vid.id)
            ).all()

            durs = [c.duration_seconds for c in db_chunks]
            avg_dur = sum(durs) / len(durs)
            print(
                f"- {vid.youtube_id} ({vid.id}):\n"
                f"    Video Status:   {vid.status}\n"
                f"    Stage Status:   {stage_status}\n"
                f"    Chunks in DB:   {len(db_chunks)}\n"
                f"    Duration Range: {min(durs):.2f}s – {max(durs):.2f}s (avg: {avg_dur:.2f}s)\n"
            )

    print("SUCCESS: 75-second chunk generation completed for all 5 Greedy videos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
