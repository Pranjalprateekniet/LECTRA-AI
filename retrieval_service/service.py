"""Read-only semantic retrieval backend for Qdrant Cloud."""

import logging
from typing import Any, Dict, List, Optional

from lectra_core.embeddings.service import EmbeddingService
from qdrant_client import QdrantClient

from retrieval_service.config import RetrievalServiceSettings, get_service_settings
from retrieval_service.schemas import RetrieveResponse, RetrieveResultItem

logger = logging.getLogger("retrieval_service.service")


class HostedRetrievalError(Exception):
    """Raised when vector retrieval encounters an unexpected backend failure."""


class HostedRetrievalUnavailableError(HostedRetrievalError):
    """Raised when Qdrant Cloud is unreachable or timing out."""


class HostedRetrievalService:
    """Encapsulates read-only vector search over Qdrant Cloud."""

    def __init__(
        self,
        settings: Optional[RetrievalServiceSettings] = None,
        embedding_service: Optional[EmbeddingService] = None,
        qdrant_client: Optional[QdrantClient] = None,
    ) -> None:
        self.settings = settings or get_service_settings()
        self.embedding_service = embedding_service or EmbeddingService()
        self.client = qdrant_client or QdrantClient(
            url=self.settings.qdrant_url,
            api_key=self.settings.qdrant_api_key,
            timeout=int(self.settings.qdrant_timeout_seconds),
        )

    def warmup(self) -> None:
        """Preload and cache the embedding model on server startup."""
        logger.info(
            "Pre-warming and caching embedding model on startup",
            extra={"model": self.settings.embedding_model_name},
        )
        try:
            self.embedding_service.embed_query("warmup initialization query")
            logger.info("Embedding model cached successfully on startup")
        except Exception as exc:
            logger.warning(
                "Embedding model warmup encountered exception",
                extra={"error": str(exc)},
            )

    def retrieve(self, query: str, top_k: int = 5) -> RetrieveResponse:
        """Embed natural-language query and search read-only Qdrant collection."""
        clean_query = query.strip()
        if not clean_query:
            return RetrieveResponse(success=True, results=[])

        # Enforce server-side top-k bound
        clamped_top_k = min(max(1, top_k), self.settings.max_top_k)

        # 1. Generate query embedding using the exact ingestion embedding model and task prompt
        try:
            query_vector = self.embedding_service.embed_query(clean_query)
        except Exception as exc:
            logger.error("Query embedding generation failed", extra={"error": str(exc)})
            raise HostedRetrievalError("Failed to generate query embedding.") from exc

        # 2. Query Qdrant Cloud collection using strictly read-only query_points
        try:
            search_res = self.client.query_points(
                collection_name=self.settings.qdrant_collection_name,
                query=query_vector,
                limit=clamped_top_k,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            # Mask internal URLs, keys, or stack traces
            logger.error("Qdrant search query failed", extra={"error": str(exc)})
            raise HostedRetrievalUnavailableError(
                "Knowledge base vector store is currently unavailable. Please try again later."
            ) from exc

        # 3. Transform points into clean RetrieveResultItems
        items: List[RetrieveResultItem] = []
        raw_points = getattr(search_res, "points", []) or []

        for point in raw_points:
            payload: Dict[str, Any] = getattr(point, "payload", {}) or {}
            score = float(getattr(point, "score", 0.0))

            text = payload.get("text")
            if not text or not str(text).strip():
                continue

            yt_id = str(payload.get("youtube_id") or "").strip()
            v_id = str(payload.get("video_id") or "").strip()
            pl_id = str(payload.get("playlist_id") or "").strip()
            ch_id = str(payload.get("chunk_id") or getattr(point, "id", "")).strip()

            try:
                start_sec = float(payload.get("start_seconds", 0.0))
            except (ValueError, TypeError):
                start_sec = 0.0

            try:
                end_sec = float(payload.get("end_seconds", 0.0))
            except (ValueError, TypeError):
                end_sec = 0.0

            try:
                duration_sec = float(
                    payload.get("duration_seconds", max(0.0, end_sec - start_sec))
                )
            except (ValueError, TypeError):
                duration_sec = max(0.0, end_sec - start_sec)

            try:
                chunk_idx = int(payload.get("chunk_index", 0))
            except (ValueError, TypeError):
                chunk_idx = 0

            # Verified timestamped YouTube citation
            if yt_id:
                youtube_url = f"https://www.youtube.com/watch?v={yt_id}&t={int(start_sec)}"
            else:
                youtube_url = str(payload.get("youtube_url") or "")

            title = str(payload.get("video_title") or payload.get("title") or "Untitled Video")

            item = RetrieveResultItem(
                video_title=title,
                text=str(text),
                start_timestamp=start_sec,
                start_seconds=start_sec,
                end_seconds=end_sec,
                duration_seconds=duration_sec,
                youtube_url=youtube_url,
                score=score,
                similarity_score=score,
                chunk_id=ch_id,
                video_id=v_id,
                youtube_id=yt_id,
                playlist_id=pl_id,
                chunk_index=chunk_idx,
            )
            items.append(item)

        items.sort(key=lambda x: x.score, reverse=True)
        return RetrieveResponse(success=True, results=items)

    def check_health(self) -> Dict[str, Any]:
        """Check operational connectivity to Qdrant without exposing credentials."""
        try:
            exists = self.client.collection_exists(self.settings.qdrant_collection_name)
            if not exists:
                return {"healthy": False, "qdrant_status": "collection_not_found"}
            return {"healthy": True, "qdrant_status": "connected"}
        except Exception as exc:
            logger.warning("Qdrant health probe failed", extra={"error": str(exc)})
            return {"healthy": False, "qdrant_status": "unreachable"}

    def close(self) -> None:
        """Release underlying model resources."""
        self.embedding_service.close()
