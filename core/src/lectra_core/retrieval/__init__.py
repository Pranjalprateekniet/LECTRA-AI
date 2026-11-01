"""Retrieval module: semantic similarity search for YouTube revision chunks."""

from lectra_core.retrieval.filters import build_qdrant_filter
from lectra_core.retrieval.schemas import (
    RetrievalFilter,
    RetrievalQuery,
    SearchResponse,
    SearchResultItem,
)
from lectra_core.retrieval.service import RetrievalError, RetrievalService

__all__ = [
    "RetrievalError",
    "RetrievalFilter",
    "RetrievalQuery",
    "RetrievalService",
    "SearchResponse",
    "SearchResultItem",
    "build_qdrant_filter",
]
