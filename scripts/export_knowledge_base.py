#!/usr/bin/env python3
"""Export existing Qdrant Cloud knowledge base into a compressed, portable distribution artifact.

Streams vectors and complete payloads from Qdrant Cloud collection `revision_chunks`
into `data/knowledge_base/chunks_7000.jsonl.gz` and writes `manifest.json`.
"""

import argparse
import gzip
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from lectra_core.config import Settings, get_settings
from qdrant_client import QdrantClient
from qdrant_client.http import models

EXPORT_FORMAT_VERSION = "1.0"
DEFAULT_OUTPUT_DIR = Path("data/knowledge_base")
DEFAULT_ARCHIVE_NAME = "chunks_7000.jsonl.gz"
DEFAULT_MANIFEST_NAME = "manifest.json"
EXPECTED_TOTAL_POINTS = 7000
EXPECTED_VECTOR_DIM = 768
EXPECTED_DISTANCE_METRIC = "Cosine"

KNOWN_PLAYLISTS = {
    "3820e00b-81b6-4f34-9e68-011ddc3d9f98": {
        "title": "Strivers A2Z-DSA Course | DSA Playlist | Placements",
        "expected_count": 6011,
    },
    "0fd210e4-904f-4127-b539-130cb1497377": {
        "title": "Generative AI using LangChain",
        "expected_count": 989,
    },
}


def get_qdrant_client(settings: Settings) -> QdrantClient:
    """Initialize Qdrant client from centralized settings without exposing credentials."""
    api_key = (
        settings.qdrant_api_key.get_secret_value()
        if hasattr(settings.qdrant_api_key, "get_secret_value")
        else settings.qdrant_api_key
    )
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=api_key,
        timeout=60,
    )


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def export_knowledge_base(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    batch_size: int = 500,
    quiet: bool = False,
) -> Tuple[Path, Path]:
    """Stream all points from Qdrant Cloud into a compressed JSONL file with manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / DEFAULT_ARCHIVE_NAME
    temp_archive_path = output_dir / f"{DEFAULT_ARCHIVE_NAME}.tmp"
    manifest_path = output_dir / DEFAULT_MANIFEST_NAME

    settings = get_settings()
    client = get_qdrant_client(settings)
    collection_name = settings.qdrant_collection_name

    if not quiet:
        print(f"Connecting to Qdrant Cloud collection: {collection_name}")

    # Inspect collection configuration
    try:
        col_info = client.get_collection(collection_name)
    except Exception as exc:
        print(f"ERROR: Failed to connect to Qdrant Cloud collection '{collection_name}': {exc}", file=sys.stderr)
        sys.exit(1)

    total_points = getattr(col_info, "points_count", 0)
    if not quiet:
        print(f"Collection status: {total_points} total points reported by Qdrant Cloud.")

    vectors_config = col_info.config.params.vectors
    vector_dimension = EXPECTED_VECTOR_DIM
    distance_metric = EXPECTED_DISTANCE_METRIC
    vector_type = "unnamed"

    if hasattr(vectors_config, "size") and vectors_config.size is not None:
        vector_dimension = vectors_config.size
        distance_metric = str(vectors_config.distance).split(".")[-1]
    elif isinstance(vectors_config, dict):
        vector_type = "named"
        # If named vectors, take the primary vector dimension
        first_key = next(iter(vectors_config))
        vector_dimension = getattr(vectors_config[first_key], "size", EXPECTED_VECTOR_DIM)
        distance_metric = str(getattr(vectors_config[first_key], "distance", EXPECTED_DISTANCE_METRIC)).split(".")[-1]

    if not quiet:
        print(f"Vector configuration: dimension={vector_dimension}, distance={distance_metric}, type={vector_type}")

    # Clean any stale temporary export file
    if temp_archive_path.exists():
        temp_archive_path.unlink()

    offset = None
    scrolled_count = 0
    seen_ids: Set[str] = set()
    playlist_counts: Dict[str, int] = {}
    playlist_titles: Dict[str, str] = {}
    uncompressed_bytes = 0
    start_time = time.time()

    if not quiet:
        print(f"Starting streaming export to {temp_archive_path} (batch size: {batch_size})...")

    # Open gzip output stream with level 9 for maximum compression
    with gzip.open(temp_archive_path, "wt", encoding="utf-8", compresslevel=9) as gz_out:
        while True:
            records, offset = client.scroll(
                collection_name=collection_name,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )

            if not records:
                break

            for rec in records:
                pid = str(rec.id)
                if pid in seen_ids:
                    print(f"WARNING: Duplicate point ID detected during scroll: {pid}", file=sys.stderr)
                    continue
                seen_ids.add(pid)

                # Format record: preserve exact id, vector, and full payload
                # Handle both unnamed vector (list) and named vectors (dict)
                vector_data = rec.vector
                payload_data = rec.payload or {}

                # Tally playlist stats
                playlist_id = payload_data.get("playlist_id", "unknown")
                playlist_counts[playlist_id] = playlist_counts.get(playlist_id, 0) + 1
                if playlist_id in KNOWN_PLAYLISTS and playlist_id not in playlist_titles:
                    playlist_titles[playlist_id] = KNOWN_PLAYLISTS[playlist_id]["title"]

                record_obj = {
                    "id": pid,
                    "vector": vector_data,
                    "payload": payload_data,
                }

                line = json.dumps(record_obj, ensure_ascii=False) + "\n"
                uncompressed_bytes += len(line.encode("utf-8"))
                gz_out.write(line)
                scrolled_count += 1

            if not quiet:
                elapsed = time.time() - start_time
                print(f"  Exported {scrolled_count}/{total_points} points... ({elapsed:.1f}s)")

            if offset is None:
                break

    # Atomically replace final archive
    if archive_path.exists():
        archive_path.unlink()
    temp_archive_path.rename(archive_path)

    export_duration = time.time() - start_time
    compressed_bytes = archive_path.stat().st_size
    archive_sha256 = compute_file_sha256(archive_path)

    # Build manifest
    manifest_data = {
        "format_version": EXPORT_FORMAT_VERSION,
        "collection_name": collection_name,
        "export_timestamp": datetime.now(timezone.utc).isoformat(),
        "archive_file": DEFAULT_ARCHIVE_NAME,
        "archive_sha256": archive_sha256,
        "compressed_size_bytes": compressed_bytes,
        "uncompressed_size_bytes": uncompressed_bytes,
        "point_count": scrolled_count,
        "vector_dimension": vector_dimension,
        "distance_metric": distance_metric,
        "vector_type": vector_type,
        "playlist_counts": playlist_counts,
        "playlist_titles": playlist_titles,
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    if not quiet:
        print("\nExport Complete!")
        print(f"  Archive: {archive_path} ({compressed_bytes / (1024*1024):.2f} MB)")
        print(f"  Uncompressed Size: {uncompressed_bytes / (1024*1024):.2f} MB")
        print(f"  SHA-256: {archive_sha256}")
        print(f"  Total points exported: {scrolled_count}")
        print(f"  Duration: {export_duration:.2f}s")
        print(f"  Manifest written: {manifest_path}")

    return archive_path, manifest_path


def verify_exported_archive(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    quiet: bool = False,
) -> bool:
    """Verify integrity of the exported knowledge base against requirements and manifest."""
    archive_path = output_dir / DEFAULT_ARCHIVE_NAME
    manifest_path = output_dir / DEFAULT_MANIFEST_NAME

    if not archive_path.exists():
        print(f"ERROR: Archive file not found at {archive_path}", file=sys.stderr)
        return False
    if not manifest_path.exists():
        print(f"ERROR: Manifest file not found at {manifest_path}", file=sys.stderr)
        return False

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if not quiet:
        print("\n=== Verifying Exported Archive Integrity ===")
        print(f"Checking SHA-256 of {archive_path}...")

    # 1. Verify SHA-256 checksum
    actual_sha256 = compute_file_sha256(archive_path)
    expected_sha256 = manifest.get("archive_sha256")
    if actual_sha256 != expected_sha256:
        print(f"ERROR: Checksum mismatch! Expected {expected_sha256}, got {actual_sha256}", file=sys.stderr)
        return False
    if not quiet:
        print(f"  SHA-256 match verified: {actual_sha256}")

    # 2. Decompress and validate all points line-by-line
    seen_ids: Set[str] = set()
    playlist_tallies: Dict[str, int] = {}
    verified_points = 0
    vector_dim_errors = 0
    null_vector_errors = 0
    invalid_json_errors = 0
    missing_fields_errors = 0

    expected_dim = manifest.get("vector_dimension", EXPECTED_VECTOR_DIM)

    with gzip.open(archive_path, "rt", encoding="utf-8") as gz_in:
        for line_num, line in enumerate(gz_in, start=1):
            line_str = line.strip()
            if not line_str:
                continue

            try:
                rec = json.loads(line_str)
            except Exception as e:
                invalid_json_errors += 1
                print(f"Line {line_num}: JSON parse error: {e}", file=sys.stderr)
                continue

            pid = rec.get("id")
            if not pid or not isinstance(pid, str):
                missing_fields_errors += 1
                continue

            if pid in seen_ids:
                print(f"Duplicate point ID found: {pid}", file=sys.stderr)
                return False
            seen_ids.add(pid)

            vector = rec.get("vector")
            if vector is None:
                null_vector_errors += 1
            elif isinstance(vector, list):
                if len(vector) != expected_dim:
                    vector_dim_errors += 1
                if any(v is None for v in vector):
                    null_vector_errors += 1
            elif isinstance(vector, dict):
                first_k = next(iter(vector))
                v_list = vector[first_k]
                if len(v_list) != expected_dim or any(v is None for v in v_list):
                    vector_dim_errors += 1

            payload = rec.get("payload")
            if not isinstance(payload, dict):
                missing_fields_errors += 1
                continue

            pl_id = payload.get("playlist_id")
            if pl_id:
                playlist_tallies[pl_id] = playlist_tallies.get(pl_id, 0) + 1

            verified_points += 1

    if not quiet:
        print(f"Verified {verified_points} points in archive.")
        print(f"Unique point IDs: {len(seen_ids)}")
        for pl_id, count in playlist_tallies.items():
            pl_info = KNOWN_PLAYLISTS.get(pl_id, {})
            name = pl_info.get("title", pl_id)
            exp = pl_info.get("expected_count", "N/A")
            print(f"  Playlist '{name}' ({pl_id}): {count} (expected: {exp})")

    # Assertions
    all_ok = True
    if verified_points != EXPECTED_TOTAL_POINTS:
        print(f"ERROR: Expected {EXPECTED_TOTAL_POINTS} points, found {verified_points}", file=sys.stderr)
        all_ok = False

    if len(seen_ids) != EXPECTED_TOTAL_POINTS:
        print(f"ERROR: Expected {EXPECTED_TOTAL_POINTS} unique IDs, found {len(seen_ids)}", file=sys.stderr)
        all_ok = False

    if vector_dim_errors > 0 or null_vector_errors > 0:
        print(f"ERROR: Vector validation errors: {vector_dim_errors} dim errors, {null_vector_errors} null errors", file=sys.stderr)
        all_ok = False

    if invalid_json_errors > 0 or missing_fields_errors > 0:
        print(f"ERROR: JSON/payload errors: {invalid_json_errors} json errors, {missing_fields_errors} missing field errors", file=sys.stderr)
        all_ok = False

    for pl_id, meta in KNOWN_PLAYLISTS.items():
        actual = playlist_tallies.get(pl_id, 0)
        expected = meta["expected_count"]
        if actual != expected:
            print(f"ERROR: Playlist {meta['title']} ({pl_id}) count mismatch: got {actual}, expected {expected}", file=sys.stderr)
            all_ok = False

    if all_ok and not quiet:
        print("ALL INTEGRITY CHECKS PASSED: Archive is 100% valid and verified.")

    return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Qdrant Cloud knowledge base to compressed distribution artifact.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write archive and manifest (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of points to scroll per request (default: 500)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing archive and manifest without re-exporting",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    args = parser.parse_args()

    if args.verify_only:
        success = verify_exported_archive(output_dir=args.output_dir, quiet=args.quiet)
        sys.exit(0 if success else 1)

    export_knowledge_base(output_dir=args.output_dir, batch_size=args.batch_size, quiet=args.quiet)
    success = verify_exported_archive(output_dir=args.output_dir, quiet=args.quiet)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

