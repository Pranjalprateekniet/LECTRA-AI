"""Targeted embedding generation and Qdrant indexing script for the five Greedy Algorithm videos.

Scanned IDs:
- II6ziNnub1Q: N meetings In One Room | Greedy Algorithm
- dxVcMDI7vyI: Minimum Platforms | Greedy Algorithms
- LjPx4wQaRIs: Job Sequencing Problem | Greedy Algorithms
- F_DDzYnxO14: Fractional Knapsack | Greedy Algorithms
- mVg9CfJvayM: Minimum Coins | Greedy Algorithms

This script operates on `data/revision_rag.db` and Qdrant Cloud.
It is strictly scoped to these 5 records (56 total chunks).
All other 320 videos in the SQLite database remain completely untouched.
"""

import sys
import time
from pathlib import Path

# Ensure core and backend packages are on path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "core" / "src"))
sys.path.insert(0, str(repo_root / "backend" / "src"))

from lectra_core.config import get_settings  # noqa: E402
from lectra_core.db.models import ProcessingStage, Video, VideoChunk  # noqa: E402
from lectra_core.db.session import get_db  # noqa: E402
from lectra_core.embeddings.model import EmbeddingModelManager  # noqa: E402
from lectra_core.embeddings.service import EmbeddingService  # noqa: E402
from lectra_core.logging import get_logger, setup_logging  # noqa: E402
from lectra_core.vectorstore.qdrant import QdrantVectorStore  # noqa: E402
from lectra_core.vectorstore.service import IndexingService  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

logger = get_logger("lectra.scripts.index_greedy_chunks")

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

    print("=" * 80)
    print("Phase 5: Embedding Generation & Qdrant Cloud Indexing for 5 Greedy Videos")
    print(f"Database:        {settings.database_url}")
    print(f"Qdrant URL:      {settings.qdrant_url}")
    print(f"Collection:      {settings.qdrant_collection_name}")
    print(f"Embedding Model: {settings.embedding_model_name}")
    print(f"Batch Size:      {settings.embedding_batch_size}")
    print("=" * 80)

    # 1. Initialize Vector Store and ensure collection
    vector_store = QdrantVectorStore(settings=settings)
    print("\n[Step 1] Ensuring Qdrant Cloud collection...")
    try:
        vector_store.ensure_collection()
        print(f"  -> Collection '{settings.qdrant_collection_name}' ready.")
    except Exception as exc:
        print(f"  ERROR ensuring collection: {exc}", file=sys.stderr)
        return 1

    # 2. Initialize embedding and indexing services
    model_mgr = EmbeddingModelManager.get_instance()
    embedding_service = EmbeddingService(settings=settings, model_manager=model_mgr)
    indexing_service = IndexingService(
        vector_store=vector_store,
        embedding_service=embedding_service,
        settings=settings,
    )

    total_chunks_indexed = 0
    start_time = time.time()

    with next(get_db(settings)) as session:
        # Verify 5 videos exist and are in CHUNKED or INDEXED status
        stmt = select(Video).where(Video.youtube_id.in_(TARGET_YOUTUBE_IDS))
        found_videos = {v.youtube_id: v for v in session.scalars(stmt).all()}

        missing = [y_id for y_id in TARGET_YOUTUBE_IDS if y_id not in found_videos]
        if missing:
            print(f"ERROR: Missing video records in database: {missing}", file=sys.stderr)
            return 1

        print("\n[Step 2] Processing 5 Greedy Algorithm Videos:")
        for idx, y_id in enumerate(TARGET_YOUTUBE_IDS, 1):
            video = found_videos[y_id]
            # Check chunks count
            chunk_count_stmt = (
                select(func.count())
                .select_from(VideoChunk)
                .where(VideoChunk.video_id == video.id)
            )
            chunk_count = session.scalar(chunk_count_stmt) or 0

            print(f"\n  [{idx}/5] Video: '{video.title}' ({video.youtube_id})")
            print(f"        Video ID:     {video.id}")
            print(f"        Chunks Count: {chunk_count}")
            print(f"        Prior Status: {video.status}")

            if chunk_count == 0:
                print("        WARNING: Video has 0 chunks! Skipping.", file=sys.stderr)
                continue

            # Run indexing
            v_start = time.time()
            result = indexing_service.index_video(
                session=session,
                video=video,
            )
            v_duration = time.time() - v_start

            total_chunks_indexed += result.chunks_indexed
            print(
                f"        Indexed & Verified: {result.chunks_indexed} points in {v_duration:.2f}s "
                f"({result.chunks_indexed/v_duration if v_duration > 0 else 0:.1f} chunks/sec)"
            )
            print(f"        Stage Status:       {result.status}")
            print(f"        Updated Video Status: {video.status}")

        # 3. Overall database verification
        print("\n[Step 3] Verifying SQLite database status:")
        total_videos = session.scalar(select(func.count()).select_from(Video))
        indexed_videos = session.scalar(
            select(func.count()).select_from(Video).where(Video.status == "INDEXED")
        )
        total_chunks = session.scalar(select(func.count()).select_from(VideoChunk))

        # Check processing stages
        indexing_stages = session.scalars(
            select(ProcessingStage).where(
                ProcessingStage.stage_name == "INDEXING",
                ProcessingStage.status == "COMPLETED",
            )
        ).all()

        print(f"  Total videos in database:       {total_videos}")
        print(f"  Indexed videos in database:     {indexed_videos}")
        print(f"  Total chunks in database:       {total_chunks}")
        print(f"  Completed INDEXING stages:      {len(indexing_stages)}")

    # 4. Check Qdrant collection stats
    print("\n[Step 4] Verifying Qdrant Cloud collection status:")
    coll_info = vector_store.client.get_collection(settings.qdrant_collection_name)
    print(f"  Collection:    {settings.qdrant_collection_name}")
    print(f"  Status:        {coll_info.status}")
    print(f"  Points Count:  {coll_info.points_count}")
    print(f"  Indexed Vectors: {coll_info.indexed_vectors_count}")

    # Unload model to release GPU memory
    model_mgr.unload_model()
    vector_store.client.close()

    total_time = time.time() - start_time
    print("\n" + "=" * 80)
    print("SUCCESS: Phase 5 Embedding Generation & Vector Indexing Complete!")
    print(f"Total chunks indexed: {total_chunks_indexed} / 56")
    print(f"Total execution time: {total_time:.2f} seconds")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
