"""Semantic retrieval service powered by EmbeddingGemma 2 and Qdrant."""

from typing import Any, Dict, List, Optional

from lectra_core.config import Settings, get_settings
from lectra_core.embeddings.service import EmbeddingService
from lectra_core.logging import get_logger
from lectra_core.retrieval.filters import build_qdrant_filter
from lectra_core.retrieval.schemas import (
    RetrievalFilter,
    RetrievalQuery,
    SearchResponse,
    SearchResultItem,
)
from lectra_core.vectorstore.qdrant import QdrantVectorStore

logger = get_logger("lectra.retrieval.service")


class RetrievalError(Exception):
    """Raised when vector retrieval encounters an unexpected backend failure."""


class RetrievalService:
    """Orchestrates query validation, embedding generation, search, and citation synthesis."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        embedding_service: Optional[EmbeddingService] = None,
        vector_store: Optional[QdrantVectorStore] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.embedding_service = embedding_service or EmbeddingService(settings=self.settings)
        self.vector_store = vector_store or QdrantVectorStore(settings=self.settings)

    def search_query(self, query_obj: RetrievalQuery) -> SearchResponse:
        """Execute semantic search from a structured RetrievalQuery schema."""
        return self.search(
            query=query_obj.query,
            top_k=query_obj.top_k,
            score_threshold=query_obj.score_threshold,
            playlist_id=query_obj.playlist_id,
            video_id=query_obj.video_id,
            youtube_id=query_obj.youtube_id,
        )

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        playlist_id: Optional[str] = None,
        video_id: Optional[str] = None,
        youtube_id: Optional[str] = None,
    ) -> SearchResponse:
        """Search relevant chunks for a natural-language query with optional metadata filters."""
        # 1. Validate and normalize query text
        if not query or not query.strip():
            raise ValueError("Query string must not be empty or whitespace only.")
        clean_query = query.strip()

        # 2. Resolve parameters
        limit = top_k if top_k is not None else self.settings.retrieval_default_top_k
        if limit < 1:
            raise ValueError(f"top_k must be at least 1, got {limit}")
        if limit > 100:
            raise ValueError(f"top_k must not exceed 100, got {limit}")

        threshold = (
            score_threshold
            if score_threshold is not None
            else self.settings.retrieval_default_score_threshold
        )
        if threshold is not None and not (0.0 <= threshold <= 1.0):
            raise ValueError(f"score_threshold must be between 0.0 and 1.0, got {threshold}")

        # 3. Build Qdrant filter
        filters = RetrievalFilter(
            playlist_id=playlist_id,
            video_id=video_id,
            youtube_id=youtube_id,
        )
        qdrant_filter = build_qdrant_filter(filters)

        # 4. Generate query embedding with official task prefix
        logger.info(
            "Generating query embedding",
            extra={"query": clean_query, "top_k": limit, "score_threshold": threshold},
        )
        try:
            query_vector = self.embedding_service.embed_query(clean_query)
        except Exception as exc:
            logger.error("Failed to generate query embedding", extra={"error": str(exc)})
            raise RetrievalError(f"Embedding generation failed: {exc}") from exc

        # 5. Query Qdrant vector index
        try:
            query_res = self.vector_store.client.query_points(
                collection_name=self.vector_store.collection_name,
                query=query_vector,
                query_filter=qdrant_filter,
                limit=limit,
                score_threshold=threshold,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            logger.error(
                "Qdrant query execution failed",
                extra={"collection": self.vector_store.collection_name, "error": str(exc)},
            )
            raise RetrievalError(
                "Vector store search failed. Please verify vector store availability."
            ) from exc

        # 6. Transform Qdrant points into SearchResultItems safely
        results: List[SearchResultItem] = []
        raw_points = getattr(query_res, "points", []) or []

        for point in raw_points:
            payload: Dict[str, Any] = getattr(point, "payload", {}) or {}
            score = float(getattr(point, "score", 0.0))

            # Validate payload integrity
            text = payload.get("text")
            if not text or not str(text).strip():
                logger.warning(
                    "Skipping point with missing or empty text payload",
                    extra={"point_id": str(getattr(point, "id", "unknown"))},
                )
                continue

            yt_id = str(payload.get("youtube_id") or "").strip()
            v_id = str(payload.get("video_id") or "").strip()
            pl_id = str(payload.get("playlist_id") or "").strip()
            ch_id = str(payload.get("chunk_id") or getattr(point, "id", "")).strip()

            # Handle start/end seconds defensively
            try:
                start_sec = float(payload.get("start_seconds", 0.0))
            except (ValueError, TypeError):
                start_sec = 0.0

            try:
                end_sec = float(payload.get("end_seconds", 0.0))
            except (ValueError, TypeError):
                end_sec = 0.0

            try:
                duration_sec = float(payload.get("duration_seconds", max(0.0, end_sec - start_sec)))
            except (ValueError, TypeError):
                duration_sec = max(0.0, end_sec - start_sec)

            try:
                chunk_idx = int(payload.get("chunk_index", 0))
            except (ValueError, TypeError):
                chunk_idx = 0

            # Construct verified timestamped YouTube URL; do not fabricate if youtube_id is absent
            if yt_id:
                youtube_url = f"https://www.youtube.com/watch?v={yt_id}&t={int(start_sec)}"
            else:
                youtube_url = ""

            title = str(payload.get("video_title") or payload.get("title") or "Untitled Video")

            item = SearchResultItem(
                chunk_id=ch_id,
                video_id=v_id,
                youtube_id=yt_id,
                playlist_id=pl_id,
                video_title=title,
                chunk_index=chunk_idx,
                text=str(text),
                start_seconds=start_sec,
                end_seconds=end_sec,
                duration_seconds=duration_sec,
                similarity_score=score,
                youtube_url=youtube_url,
            )
            results.append(item)

        # Ensure results are sorted descending by similarity score
        results.sort(key=lambda r: r.similarity_score, reverse=True)

        return SearchResponse(
            query=clean_query,
            results=results,
            total_results=len(results),
        )

    def close(self) -> None:
        """Release underlying embedding model resources."""
        self.embedding_service.close()
