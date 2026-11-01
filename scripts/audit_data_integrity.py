"""Comprehensive data integrity audit verifying consistency between SQLite and Qdrant."""

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

import sqlite3
from lectra_core.config import get_settings
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Record


def run_data_integrity_audit() -> Dict[str, Any]:
    settings = get_settings()
    db_path = Path("data/revision_rag.db")
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    # 1. Connect to SQLite
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Load SQLite chunks
    cur.execute(
        """
        SELECT c.id, c.video_id, c.chunk_index, c.start_seconds, c.end_seconds,
               c.duration_seconds, c.text, c.token_count,
               v.youtube_id, v.playlist_id, v.title as video_title,
               p.youtube_id as playlist_youtube_id, p.title as playlist_title
        FROM video_chunks c
        JOIN videos v ON c.video_id = v.id
        JOIN playlists p ON v.playlist_id = p.id
        ORDER BY v.youtube_id, c.chunk_index
        """
    )
    sqlite_chunks = [dict(row) for row in cur.fetchall()]
    sqlite_chunk_map = {c["id"]: c for c in sqlite_chunks}

    # 2. Connect to Qdrant Cloud
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    col_name = settings.qdrant_collection_name
    col_info = client.get_collection(col_name)

    # Fetch all points from Qdrant with vectors and payloads
    qdrant_points: List[Record] = []
    offset = None
    while True:
        records, next_offset = client.scroll(
            collection_name=col_name,
            limit=100,
            with_payload=True,
            with_vectors=True,
            offset=offset,
        )
        qdrant_points.extend(records)
        if next_offset is None:
            break
        offset = next_offset

    qdrant_point_map = {str(p.id): p for p in qdrant_points}

    # 3. Verifications
    total_sqlite_chunks = len(sqlite_chunks)
    total_qdrant_points = len(qdrant_points)

    missing_in_qdrant = []
    orphan_in_qdrant = []
    vector_dimension_failures = []
    normalization_failures = []
    metadata_mismatches = []
    timestamp_mismatches = []

    # Verification A: Check that every SQLite chunk exists in Qdrant with matching attributes
    for chunk_id, chunk in sqlite_chunk_map.items():
        if chunk_id not in qdrant_point_map:
            missing_in_qdrant.append(chunk_id)
            continue

        point = qdrant_point_map[chunk_id]
        payload = point.payload or {}

        # Vector dimension check
        vec = point.vector
        if not isinstance(vec, list) or len(vec) != 768:
            vector_dimension_failures.append({
                "chunk_id": chunk_id,
                "expected": 768,
                "actual": len(vec) if isinstance(vec, list) else None,
            })
        else:
            # Check vector finite and normalized (norm close to 1.0)
            norm = math.sqrt(sum(x * x for x in vec))
            if any(math.isnan(x) or math.isinf(x) for x in vec):
                normalization_failures.append({
                    "chunk_id": chunk_id,
                    "reason": "non-finite-values",
                })
            elif abs(norm - 1.0) > 0.05:  # EmbeddingGemma vectors normalized to unit length
                normalization_failures.append({
                    "chunk_id": chunk_id,
                    "norm": norm,
                    "reason": f"norm {norm:.4f} exceeds tolerance",
                })

        # Payload metadata checks
        if payload.get("video_id") != chunk["video_id"]:
            metadata_mismatches.append({
                "chunk_id": chunk_id,
                "field": "video_id",
                "sqlite": chunk["video_id"],
                "qdrant": payload.get("video_id"),
            })
        if payload.get("playlist_id") != chunk["playlist_id"]:
            metadata_mismatches.append({
                "chunk_id": chunk_id,
                "field": "playlist_id",
                "sqlite": chunk["playlist_id"],
                "qdrant": payload.get("playlist_id"),
            })
        if payload.get("youtube_id") != chunk["youtube_id"]:
            metadata_mismatches.append({
                "chunk_id": chunk_id,
                "field": "youtube_id",
                "sqlite": chunk["youtube_id"],
                "qdrant": payload.get("youtube_id"),
            })

        # Timestamp checks (within 0.01s tolerance)
        q_start = payload.get("start_seconds")
        q_end = payload.get("end_seconds")
        if q_start is None or abs(float(q_start) - float(chunk["start_seconds"])) > 0.01:
            timestamp_mismatches.append({
                "chunk_id": chunk_id,
                "field": "start_seconds",
                "sqlite": chunk["start_seconds"],
                "qdrant": q_start,
            })
        if q_end is None or abs(float(q_end) - float(chunk["end_seconds"])) > 0.01:
            timestamp_mismatches.append({
                "chunk_id": chunk_id,
                "field": "end_seconds",
                "sqlite": chunk["end_seconds"],
                "qdrant": q_end,
            })

    # Verification B: Check for orphan points in Qdrant not in SQLite
    for pt_id in qdrant_point_map:
        if pt_id not in sqlite_chunk_map:
            orphan_in_qdrant.append(pt_id)

    # 4. Compile Audit Report
    all_passed = (
        total_sqlite_chunks == total_qdrant_points
        and len(missing_in_qdrant) == 0
        and len(orphan_in_qdrant) == 0
        and len(vector_dimension_failures) == 0
        and len(normalization_failures) == 0
        and len(metadata_mismatches) == 0
        and len(timestamp_mismatches) == 0
    )

    audit_result = {
        "status": "PASS" if all_passed else "FAIL",
        "timestamp": "2026-11-01T19:35:00Z",
        "collection_name": col_name,
        "sqlite_chunk_count": total_sqlite_chunks,
        "qdrant_point_count": total_qdrant_points,
        "counts_agree": total_sqlite_chunks == total_qdrant_points,
        "vector_dimension_configured": col_info.config.params.vectors.size,
        "distance_metric": str(col_info.config.params.vectors.distance),
        "missing_in_qdrant_count": len(missing_in_qdrant),
        "orphan_in_qdrant_count": len(orphan_in_qdrant),
        "vector_dimension_failures_count": len(vector_dimension_failures),
        "normalization_failures_count": len(normalization_failures),
        "metadata_mismatches_count": len(metadata_mismatches),
        "timestamp_mismatches_count": len(timestamp_mismatches),
        "details": {
            "missing_in_qdrant": missing_in_qdrant,
            "orphan_in_qdrant": orphan_in_qdrant,
            "vector_dimension_failures": vector_dimension_failures,
            "normalization_failures": normalization_failures,
            "metadata_mismatches": metadata_mismatches,
            "timestamp_mismatches": timestamp_mismatches,
        },
    }

    report_path = Path("reports/phase9_data_integrity.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(audit_result, f, indent=2)

    print(json.dumps(audit_result, indent=2))
    return audit_result


if __name__ == "__main__":
    res = run_data_integrity_audit()
    if res["status"] != "PASS":
        sys.exit(1)

