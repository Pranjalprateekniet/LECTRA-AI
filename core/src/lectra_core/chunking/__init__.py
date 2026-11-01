"""Chunking package for Revision RAG."""

from lectra_core.chunking.deduplicator import deduplicate_rolling_captions
from lectra_core.chunking.service import ChunkingService
from lectra_core.chunking.tokenizer import count_tokens

__all__ = ["ChunkingService", "deduplicate_rolling_captions", "count_tokens"]
