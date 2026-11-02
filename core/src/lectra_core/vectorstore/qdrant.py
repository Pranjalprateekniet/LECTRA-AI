"""Qdrant client and collection management for Revision RAG."""

from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Sequence

from qdrant_client import QdrantClient, models

from lectra_core.config import Settings, get_settings
from lectra_core.logging import get_logger

logger = get_logger("lectra.vectorstore.qdrant")

EXPECTED_VECTOR_SIZE = 768

# In-process singleton cache for local Qdrant clients (prevents portalocker concurrency crashes)
_LOCAL_CLIENTS: Dict[str, QdrantClient] = {}
_LOCAL_CLIENT_LOCK = threading.Lock()


def get_local_qdrant_client(path: str | Path) -> QdrantClient:
    """Return a thread-safe singleton QdrantClient for a local storage path.

    Prevents multiple instances from locking the local database concurrently in the same process.
    """
    canonical_path = str(Path(path).resolve())
    with _LOCAL_CLIENT_LOCK:
        if canonical_path not in _LOCAL_CLIENTS:
            try:
                _LOCAL_CLIENTS[canonical_path] = QdrantClient(path=canonical_path)
            except RuntimeError as exc:
                if "already accessed by another instance" in str(exc):
                    raise RuntimeError(
                        f"Local Qdrant database at '{canonical_path}' is locked by another process. "
                        "Ensure no other instance of Revision RAG, a background worker, or importer script is running."
                    ) from exc
                raise
        return _LOCAL_CLIENTS[canonical_path]


def close_local_qdrant_clients() -> None:
    """Close and clear all cached local Qdrant clients (useful for cleanup and tests)."""
    with _LOCAL_CLIENT_LOCK:
        for client in _LOCAL_CLIENTS.values():
            try:
                client.close()
            except Exception:
                pass
        _LOCAL_CLIENTS.clear()


class IncompatibleCollectionError(Exception):
    """Raised when an existing collection has incompatible dimension or distance metric."""


class QdrantVectorStore:
    """Manages collection lifecycle, payload schemas, and idempotent upserts in Qdrant."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[QdrantClient] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.collection_name = self.settings.qdrant_collection_name

        if client is not None:
            self.client = client
            self.is_local = False
        elif self.settings.app_mode == "USER":
            # In USER mode, always use local persistent Qdrant
            local_path = self.settings.qdrant_path
            self.client = get_local_qdrant_client(local_path)
            self.is_local = True
        elif self.settings.qdrant_url:
            # DEVELOPER mode with cloud / remote Qdrant URL
            self.client = QdrantClient(
                url=self.settings.qdrant_url,
                api_key=self.settings.qdrant_api_key,
                timeout=30,
            )
            self.is_local = False
        else:
            # DEVELOPER mode fallback to local Qdrant path
            local_path = self.settings.qdrant_path
            self.client = get_local_qdrant_client(local_path)
            self.is_local = True

    def close(self) -> None:
        """Close connection if running as a remote client."""
        if not self.is_local:
            try:
                self.client.close()
            except Exception:
                pass

    def ensure_collection(self) -> None:
        """Verify that the target collection exists and is valid, creating it if absent.

        Never deletes or alters an incompatible collection automatically.
        """
        if not self.client.collection_exists(self.collection_name):
            logger.info(
                "Collection absent; creating Qdrant collection",
                extra={
                    "collection": self.collection_name,
                    "dimension": EXPECTED_VECTOR_SIZE,
                    "metric": "Cosine",
                },
            )
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=EXPECTED_VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            )
            # Create payload indexes for fast filtered lookups
            self._create_payload_indexes()
            return

        # Collection exists: validate configuration
        info = self.client.get_collection(self.collection_name)
        params = info.config.params.vectors

        # In Qdrant, params can be a VectorParams or a dict of VectorParams
        actual_size: Optional[int] = None
        actual_dist: Any = None
        if isinstance(params, dict):
            # Named vectors
            first_vector = next(iter(params.values()))
            actual_size = first_vector.size
            actual_dist = first_vector.distance
        elif params is not None:
            actual_size = getattr(params, "size", None)
            actual_dist = getattr(params, "distance", None)

        if actual_size != EXPECTED_VECTOR_SIZE:
            raise IncompatibleCollectionError(
                f"Collection '{self.collection_name}' exists with vector dimension {actual_size}, "
                f"but {EXPECTED_VECTOR_SIZE} is required."
            )

        if actual_dist not in (models.Distance.COSINE, "Cosine"):
            raise IncompatibleCollectionError(
                f"Collection '{self.collection_name}' exists with distance metric {actual_dist}, "
                f"but Cosine is required."
            )

        logger.info(
            "Validated existing Qdrant collection",
            extra={"collection": self.collection_name, "points_count": info.points_count},
        )
        self._create_payload_indexes()

    def _create_payload_indexes(self) -> None:
        """Create keyword indexes on frequently filtered payload fields."""
        if self.is_local:
            # Local embedded Qdrant does not require or use explicit payload keyword indexes
            return

        fields = ["video_id", "youtube_id", "playlist_id"]
        for field in fields:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception as exc:
                # If index already exists or client raises notice, log and proceed
                logger.debug(f"Payload index creation for '{field}': {exc}")

    def upsert_points(
        self,
        points: Sequence[models.PointStruct],
        batch_size: int = 64,
    ) -> None:
        """Batch-upsert point structures idempotently into Qdrant."""
        if not points:
            return

        for i in range(0, len(points), batch_size):
            batch = list(points[i : i + batch_size])
            self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
                wait=True,
            )

    def retrieve_points(self, point_ids: Sequence[str]) -> List[Any]:
        """Fetch points by ID to verify successful ingestion."""
        if not point_ids:
            return []
        return list(
            self.client.retrieve(
                collection_name=self.collection_name,
                ids=list(point_ids),
                with_payload=True,
                with_vectors=False,
            )
        )

    def delete_points_by_video_id(self, video_id: str) -> None:
        """Remove all points associated with a video_id."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="video_id",
                            match=models.MatchValue(value=video_id),
                        )
                    ]
                )
            ),
        )
