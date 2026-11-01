"""Embedding generation service for documents, chunks, and search queries.

Uses google/embeddinggemma-2 with official Google DeepMind prompt templates,
attention-mask-weighted mean pooling, and L2 unit normalization.
"""

from typing import Any, List, Optional, Sequence, Tuple

import torch
import torch.nn.functional as F

from lectra_core.config import Settings, get_settings
from lectra_core.db.models import VideoChunk
from lectra_core.embeddings.model import EmbeddingModelManager
from lectra_core.logging import get_logger

logger = get_logger("lectra.embeddings.service")

DOCUMENT_PROMPT_TEMPLATE = "title: {title} | text: {text}"
QUERY_PROMPT_TEMPLATE = "task: search result | query: {query}"
EXPECTED_EMBEDDING_DIM = 768


def format_document_text(title: Optional[str], text: str) -> str:
    """Format document text with the official EmbeddingGemma 2 document prefix."""
    clean_title = title.strip() if title and title.strip() else "none"
    return DOCUMENT_PROMPT_TEMPLATE.format(title=clean_title, text=text.strip())


def format_query_text(query: str) -> str:
    """Format search query with the official EmbeddingGemma 2 query task prefix."""
    return QUERY_PROMPT_TEMPLATE.format(query=query.strip())


class EmbeddingService:
    """Service for batch-generating 768-dimensional normalized embeddings."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        model_manager: Optional[EmbeddingModelManager] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model_manager = model_manager or EmbeddingModelManager.get_instance()

    def _mean_pooling(
        self,
        last_hidden_state: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> torch.Tensor:
        """Calculate attention-mask-weighted mean pooling over token embeddings."""
        # Expand attention_mask to match hidden_state shape [batch_size, seq_len, hidden_dim]
        mask_expanded = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
        sum_embeddings = torch.sum(last_hidden_state * mask_expanded, dim=1)
        sum_mask = torch.clamp(mask_expanded.sum(dim=1), min=1e-9)
        return sum_embeddings / sum_mask

    def _embed_batch(
        self,
        model: Any,
        tokenizer: Any,
        device: str,
        formatted_texts: List[str],
    ) -> List[List[float]]:
        """Encode a batch of pre-formatted strings into normalized 768d float vectors."""
        if not formatted_texts:
            return []

        inputs = tokenizer(
            formatted_texts,
            padding=True,
            truncation=True,
            max_length=2048,
            return_tensors="pt",
        )
        if hasattr(inputs, "to"):
            inputs = inputs.to(device)
        else:
            inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}

        with torch.inference_mode():
            outputs = model(**inputs)
            pooled = self._mean_pooling(outputs.last_hidden_state, inputs["attention_mask"])
            normalized = F.normalize(pooled, p=2, dim=1)

            # Validate vector dimensions
            if normalized.shape[-1] != EXPECTED_EMBEDDING_DIM:
                dim = normalized.shape[-1]
                raise ValueError(
                    f"Expected embedding dimension {EXPECTED_EMBEDDING_DIM}, got {dim}"
                )

            return normalized.cpu().tolist()

    def embed_documents(
        self,
        documents: Sequence[Tuple[Optional[str], str]],
        batch_size: Optional[int] = None,
    ) -> List[List[float]]:
        """Embed a sequence of (title, text) documents using official document formatting."""
        if not documents:
            return []

        bs = batch_size or self.settings.embedding_batch_size
        model, tokenizer, device = self.model_manager.get_model_and_tokenizer(
            self.settings.embedding_model_name,
            self.settings.embedding_device,
        )

        formatted = [format_document_text(title, text) for title, text in documents]
        results: List[List[float]] = []

        for i in range(0, len(formatted), bs):
            batch = formatted[i : i + bs]
            embeddings = self._embed_batch(model, tokenizer, device, batch)
            results.extend(embeddings)

        return results

    def embed_chunks(
        self,
        chunks: Sequence[VideoChunk],
        video_title: str,
        batch_size: Optional[int] = None,
    ) -> List[List[float]]:
        """Convenience method to embed a sequence of VideoChunk ORM models."""
        documents = [(video_title, c.text) for c in chunks]
        return self.embed_documents(documents, batch_size=batch_size)

    def embed_query(self, query: str) -> List[float]:
        """Embed a single search query using the official query task prefix."""
        if not query or not query.strip():
            raise ValueError("Query string must not be empty.")

        model, tokenizer, device = self.model_manager.get_model_and_tokenizer(
            self.settings.embedding_model_name,
            self.settings.embedding_device,
        )
        formatted = [format_query_text(query)]
        embeddings = self._embed_batch(model, tokenizer, device, formatted)
        return embeddings[0]

    def close(self) -> None:
        """Release cached model weights and PyTorch CUDA cache."""
        self.model_manager.unload_model()
