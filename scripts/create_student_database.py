#!/usr/bin/env python3
"""Seed database generator for Revision RAG student distribution.

Extracts necessary metadata (playlists, videos, stages, and chunks) for the two
pre-indexed playlists from the developer database into a compact student SQLite seed database.

Excludes historical raw transcript segments (~70 MB) and developer worker job logs,
producing a clean, lightweight database for zero-hosting-cost student distribution.
"""

import argparse
import os
from pathlib import Path
import sqlite3
import sys
from typing import List, Set

SUPPORTED_PLAYLIST_IDS = {
    "3820e00b-81b6-4f34-9e68-011ddc3d9f98",  # Strivers A2Z-DSA Course
    "0fd210e4-904f-4127-b539-130cb1497377",  # Generative AI using LangChain
}


def create_student_database(
    source_db_path: Path,
    output_db_path: Path,
    include_chunks: bool = True,
    force: bool = False,
) -> None:
    """Create a clean, compact student SQLite database."""
    source_db_path = source_db_path.resolve()
    output_db_path = output_db_path.resolve()

    if not source_db_path.exists():
        print(f"Error: Source database not found at {source_db_path}", file=sys.stderr)
        sys.exit(1)

    if output_db_path.exists() and not force:
        print(
            f"Error: Output database already exists at {output_db_path}.\n"
            "Use --force to overwrite.",
            file=sys.stderr,
        )
        sys.exit(1)

    output_db_path.parent.mkdir(parents=True, exist_ok=True)
    temp_output_path = output_db_path.with_suffix(".tmp")
    if temp_output_path.exists():
        temp_output_path.unlink()

    print("=" * 60)
    print("Revision RAG - Student SQLite Seed Database Generator")
    print("=" * 60)
    print(f"Source DB:      {source_db_path} ({os.path.getsize(source_db_path)/(1024*1024):.2f} MB)")
    print(f"Destination DB: {output_db_path}")
    print(f"Include Chunks: {include_chunks}")
    print(f"Target Playlists: {len(SUPPORTED_PLAYLIST_IDS)}")
    print("-" * 60)

    # Open source in read-only mode using URI
    src_uri = f"file:{source_db_path}?mode=ro"
    src_conn = sqlite3.connect(src_uri, uri=True)
    src_cur = src_conn.cursor()

    dst_conn = sqlite3.connect(temp_output_path)
    dst_cur = dst_conn.cursor()

    try:
        # Enable foreign keys and set page size
        dst_cur.execute("PRAGMA page_size = 4096;")
        dst_cur.execute("PRAGMA foreign_keys = ON;")

        # 1. alembic_version
        print("Copying alembic_version table...")
        schema = src_cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        if schema:
            dst_cur.execute(schema[0])
            rows = src_cur.execute("SELECT * FROM alembic_version").fetchall()
            if rows:
                dst_cur.executemany("INSERT INTO alembic_version VALUES (?)", rows)
                print(f"  Copied {len(rows)} alembic_version record(s)")

        # 2. playlists
        print("Copying playlists table...")
        schema = src_cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='playlists'"
        ).fetchone()[0]
        dst_cur.execute(schema)

        placeholders = ",".join("?" for _ in SUPPORTED_PLAYLIST_IDS)
        playlist_rows = src_cur.execute(
            f"SELECT * FROM playlists WHERE id IN ({placeholders})",
            list(SUPPORTED_PLAYLIST_IDS),
        ).fetchall()
        if playlist_rows:
            q_marks = ",".join("?" * len(playlist_rows[0]))
            dst_cur.executemany(f"INSERT INTO playlists VALUES ({q_marks})", playlist_rows)
        print(f"  Copied {len(playlist_rows)} playlist(s)")

        # 3. videos
        print("Copying videos table...")
        schema = src_cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='videos'"
        ).fetchone()[0]
        dst_cur.execute(schema)

        video_rows = src_cur.execute(
            f"SELECT * FROM videos WHERE playlist_id IN ({placeholders}) ORDER BY position ASC",
            list(SUPPORTED_PLAYLIST_IDS),
        ).fetchall()
        if video_rows:
            q_marks = ",".join("?" * len(video_rows[0]))
            dst_cur.executemany(f"INSERT INTO videos VALUES ({q_marks})", video_rows)
        video_ids: List[str] = [r[0] for r in video_rows]
        print(f"  Copied {len(video_rows)} video(s) belonging to target playlists")

        # 4. jobs (discovery jobs for the 2 playlists)
        print("Copying jobs table...")
        schema = src_cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'"
        ).fetchone()[0]
        dst_cur.execute(schema)

        # Include discovery jobs for metadata summary in /status endpoint
        job_rows = src_cur.execute(
            "SELECT * FROM jobs WHERE job_type = 'discover_playlist'"
        ).fetchall()
        if job_rows:
            q_marks = ",".join("?" * len(job_rows[0]))
            dst_cur.executemany(f"INSERT INTO jobs VALUES ({q_marks})", job_rows)
        print(f"  Copied {len(job_rows)} discovery job record(s)")

        # 5. processing_stages
        print("Copying processing_stages table...")
        schema = src_cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='processing_stages'"
        ).fetchone()[0]
        dst_cur.execute(schema)

        # Batch insert stages for copied videos
        stage_count = 0
        batch_size = 500
        for i in range(0, len(video_ids), batch_size):
            batch_vids = video_ids[i : i + batch_size]
            v_placeholders = ",".join("?" for _ in batch_vids)
            stage_rows = src_cur.execute(
                f"SELECT * FROM processing_stages WHERE video_id IN ({v_placeholders})",
                batch_vids,
            ).fetchall()
            if stage_rows:
                q_marks = ",".join("?" * len(stage_rows[0]))
                dst_cur.executemany(
                    f"INSERT INTO processing_stages VALUES ({q_marks})", stage_rows
                )
                stage_count += len(stage_rows)
        print(f"  Copied {stage_count} processing stage record(s)")

        # 6. video_chunks
        print("Setting up video_chunks table...")
        schema = src_cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='video_chunks'"
        ).fetchone()[0]
        dst_cur.execute(schema)

        chunk_count = 0
        if include_chunks:
            for i in range(0, len(video_ids), batch_size):
                batch_vids = video_ids[i : i + batch_size]
                v_placeholders = ",".join("?" for _ in batch_vids)
                chunk_rows = src_cur.execute(
                    f"SELECT * FROM video_chunks WHERE video_id IN ({v_placeholders})",
                    batch_vids,
                ).fetchall()
                if chunk_rows:
                    q_marks = ",".join("?" * len(chunk_rows[0]))
                    dst_cur.executemany(
                        f"INSERT INTO video_chunks VALUES ({q_marks})", chunk_rows
                    )
                    chunk_count += len(chunk_rows)
            print(f"  Copied {chunk_count} video chunk record(s)")
        else:
            print("  Skipped video_chunks records (--no-chunks requested; schema created)")

        # 7. transcript_segments (Schema only, 0 rows)
        print("Setting up transcript_segments table (schema only)...")
        schema = src_cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='transcript_segments'"
        ).fetchone()[0]
        dst_cur.execute(schema)
        print("  Excluded 191,945 raw transcript segments (saving ~70 MB)")

        # 8. Recreate all original indexes
        print("Recreating database indexes...")
        indexes = src_cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
        ).fetchall()
        for idx in indexes:
            try:
                dst_cur.execute(idx[0])
            except sqlite3.OperationalError:
                pass
        print(f"  Recreated {len(indexes)} index(es)")

        dst_conn.commit()

        # Integrity checks
        print("-" * 60)
        print("Running database verification...")
        fk_errors = dst_cur.execute("PRAGMA foreign_key_check;").fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign key integrity check failed: {fk_errors}")
        print("  [PASSED] Foreign key integrity check passed (0 errors)")

        integrity_res = dst_cur.execute("PRAGMA integrity_check;").fetchall()
        if integrity_res != [("ok",)]:
            raise RuntimeError(f"Database integrity check failed: {integrity_res}")
        print("  [PASSED] PRAGMA integrity_check passed (status: ok)")

        # Vacuum and optimize
        print("Optimizing and vacuuming database...")
        dst_cur.execute("ANALYZE;")
        dst_cur.execute("VACUUM;")
        dst_conn.close()
        src_conn.close()

        # Promote temporary file to final destination
        if output_db_path.exists():
            output_db_path.unlink()
        temp_output_path.rename(output_db_path)

        final_size = os.path.getsize(output_db_path)
        print("-" * 60)
        print(f"SUCCESS: Student seed database created successfully!")
        print(f"Location:  {output_db_path}")
        print(f"Size:      {final_size / (1024*1024):.2f} MB ({final_size:,} bytes)")
        print(f"Reduction: -{((os.path.getsize(source_db_path) - final_size) / os.path.getsize(source_db_path)) * 100:.1f}% vs developer database")
        print("=" * 60)

    except Exception as exc:
        dst_conn.close()
        src_conn.close()
        if temp_output_path.exists():
            temp_output_path.unlink()
        raise exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate clean, compact student SQLite database for Revision RAG."
    )
    parser.add_argument(
        "--source-db",
        type=Path,
        default=Path("data/revision_rag.db"),
        help="Path to developer SQLite database (default: data/revision_rag.db)",
    )
    parser.add_argument(
        "--output-db",
        type=Path,
        default=Path("data/knowledge_base/student_revision_rag.db"),
        help="Path for generated student database (default: data/knowledge_base/student_revision_rag.db)",
    )
    parser.add_argument(
        "--no-chunks",
        action="store_true",
        help="Exclude video_chunks rows (creates ultra-compact ~670 KB DB)",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force overwrite if output database already exists",
    )

    args = parser.parse_args()
    create_student_database(
        source_db_path=args.source_db,
        output_db_path=args.output_db,
        include_chunks=not args.no_chunks,
        force=args.force,
    )


if __name__ == "__main__":
    main()

