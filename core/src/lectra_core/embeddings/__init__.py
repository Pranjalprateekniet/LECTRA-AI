"""Embeddings package for Revision RAG."""

from lectra_core.embeddings.model import EmbeddingModelManager, resolve_embedding_device
from lectra_core.embeddings.service import (
    DOCUMENT_PROMPT_TEMPLATE,
    EXPECTED_EMBEDDING_DIM,
    QUERY_PROMPT_TEMPLATE,
    EmbeddingService,
    format_document_text,
    format_query_text,
)

__all__ = [
    "DOCUMENT_PROMPT_TEMPLATE",
    "EXPECTED_EMBEDDING_DIM",
    "EmbeddingModelManager",
    "EmbeddingService",
    "QUERY_PROMPT_TEMPLATE",
    "format_document_text",
    "format_query_text",
    "resolve_embedding_device",
]
