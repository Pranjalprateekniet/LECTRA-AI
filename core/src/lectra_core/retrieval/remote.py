"""Remote retrieval client connecting the local backend to the hosted retrieval API."""

from typing import List, Optional

import httpx

from lectra_core.config import Settings, get_settings
from lectra_core.logging import get_logger
from lectra_core.retrieval.schemas import (
    RetrievalQuery,
    SearchResponse,
    SearchResultItem,
)
from lectra_core.retrieval.service import RetrievalError

logger = get_logger("lectra.retrieval.remote")


class RemoteRetrievalService:
    """Client for querying the central hosted read-only retrieval API."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._custom_client = client

    def _get_target_endpoint(self) -> str:
        """Resolve full retrieval URL from configured settings."""
        base = self.settings.retrieval_api_url
        if not base:
            raise RetrievalError(
                "RETRIEVAL_API_URL is not configured. Please specify the hosted retrieval API URL."
            )
        clean_base = base.rstrip("/")
        if clean_base.endswith("/retrieve"):
            return clean_base
        if clean_base.endswith("/api/v1"):
            return f"{clean_base}/retrieve"
        return f"{clean_base}/api/v1/retrieve"

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
        """Search relevant chunks via hosted retrieval endpoint."""
        if not query or not query.strip():
            raise ValueError("Query string must not be empty or whitespace only.")
        clean_query = query.strip()

        limit = top_k if top_k is not None else self.settings.retrieval_default_top_k
        if limit < 1:
            raise ValueError(f"top_k must be at least 1, got {limit}")
        # Hosted retrieval endpoint enforces server-side maximum top-k of 10
        clamped_top_k = min(limit, 10)

        target_url = self._get_target_endpoint()
        payload = {"query": clean_query, "top_k": clamped_top_k}

        logger.info(
            "Querying hosted retrieval API",
            extra={"url": target_url, "query": clean_query, "top_k": clamped_top_k},
        )

        try:
            if self._custom_client:
                response = self._custom_client.post(target_url, json=payload)
            else:
                with httpx.Client(timeout=self.settings.retrieval_api_timeout_seconds) as client:
                    response = client.post(target_url, json=payload)
        except httpx.TimeoutException as exc:
            logger.error("Hosted retrieval service timed out", extra={"error": str(exc)})
            raise RetrievalError("Hosted retrieval service request timed out.") from exc
        except httpx.RequestError as exc:
            logger.error("Failed to reach hosted retrieval service", extra={"error": str(exc)})
            raise RetrievalError(
                f"Could not connect to hosted retrieval service at {target_url}."
            ) from exc

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "a few")
            raise RetrievalError(
                f"Hosted retrieval rate limit reached. "
                f"Please wait {retry_after} seconds before querying again."
            )
        elif response.status_code == 503:
            raise RetrievalError(
                "Hosted retrieval service or vector store is currently unavailable. "
                "Please try again shortly."
            )
        elif response.status_code == 504:
            raise RetrievalError("Hosted retrieval service timed out while processing.")
        elif response.status_code >= 400:
            logger.error(
                "Hosted retrieval returned error status",
                extra={"status_code": response.status_code, "body": response.text[:200]},
            )
            raise RetrievalError(f"Hosted retrieval failed with status {response.status_code}.")

        try:
            data = response.json()
        except Exception as exc:
            logger.error(
                "Failed to decode JSON from hosted retrieval response",
                extra={"error": str(exc)},
            )
            raise RetrievalError(
                "Invalid response received from hosted retrieval service."
            ) from exc

        raw_results = data.get("results", []) or []
        items: List[SearchResultItem] = []

        for r in raw_results:
            text = str(r.get("text") or "").strip()
            if not text:
                continue

            yt_id = str(r.get("youtube_id") or "").strip()
            v_id = str(r.get("video_id") or "").strip()
            pl_id = str(r.get("playlist_id") or "").strip()
            ch_id = str(r.get("chunk_id") or "").strip()
            title = str(r.get("video_title") or r.get("title") or "Untitled Video")

            try:
                start_sec = float(r.get("start_seconds", r.get("start_timestamp", 0.0)))
            except (ValueError, TypeError):
                start_sec = 0.0

            try:
                end_sec = float(r.get("end_seconds", 0.0))
            except (ValueError, TypeError):
                end_sec = 0.0

            try:
                duration_sec = float(
                    r.get("duration_seconds", max(0.0, end_sec - start_sec))
                )
            except (ValueError, TypeError):
                duration_sec = max(0.0, end_sec - start_sec)

            try:
                score = float(r.get("similarity_score", r.get("score", 0.0)))
            except (ValueError, TypeError):
                score = 0.0

            try:
                chunk_idx = int(r.get("chunk_index", 0))
            except (ValueError, TypeError):
                chunk_idx = 0

            youtube_url = str(r.get("youtube_url") or "")
            if not youtube_url and yt_id:
                youtube_url = f"https://www.youtube.com/watch?v={yt_id}&t={int(start_sec)}"

            item = SearchResultItem(
                chunk_id=ch_id,
                video_id=v_id,
                youtube_id=yt_id,
                playlist_id=pl_id,
                video_title=title,
                chunk_index=chunk_idx,
                text=text,
                start_seconds=start_sec,
                end_seconds=end_sec,
                duration_seconds=duration_sec,
                similarity_score=score,
                youtube_url=youtube_url,
            )

            # Optional client-side filtering if requested
            if playlist_id and item.playlist_id and item.playlist_id != playlist_id:
                continue
            if video_id and item.video_id and item.video_id != video_id:
                continue
            if youtube_id and item.youtube_id and item.youtube_id != youtube_id:
                continue
            if score_threshold is not None and item.similarity_score < score_threshold:
                continue

            items.append(item)

        items.sort(key=lambda x: x.similarity_score, reverse=True)

        return SearchResponse(
            query=clean_query,
            results=items,
            total_results=len(items),
        )

    def close(self) -> None:
        """No-op for remote retrieval service."""
        pass
