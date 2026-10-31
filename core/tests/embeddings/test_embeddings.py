"""Unit tests for EmbeddingGemma 2 embedding service."""

from unittest.mock import MagicMock

import pytest
import torch
from lectra_core.config import Settings
from lectra_core.embeddings.model import EmbeddingModelManager, resolve_embedding_device
from lectra_core.embeddings.service import (
    EXPECTED_EMBEDDING_DIM,
    EmbeddingService,
    format_document_text,
    format_query_text,
)


def test_document_and_query_formatting():
    """Verify official document and query prompt formatting for EmbeddingGemma 2."""
    doc = format_document_text("Greedy Algorithms", "Take highest ratio item")
    assert doc == "title: Greedy Algorithms | text: Take highest ratio item"

    doc_no_title = format_document_text(None, "No title content")
    assert doc_no_title == "title: none | text: No title content"

    query = format_query_text("How does greedy knapsack work?")
    assert query == "task: search result | query: How does greedy knapsack work?"


def test_device_resolution():
    """Verify execution device selection with graceful CPU fallback."""
    assert resolve_embedding_device("cpu") == "cpu"
    # Auto or cuda should resolve to cuda if available, else cpu
    res = resolve_embedding_device("cuda")
    if torch.cuda.is_available():
        assert res == "cuda"
    else:
        assert res == "cpu"


def test_mean_pooling_and_normalization():
    """Verify attention-mask-weighted mean pooling and L2 unit length."""
    service = EmbeddingService(settings=Settings())

    # Simulated hidden state: batch_size=2, seq_len=3, dim=4
    hidden = torch.tensor(
        [
            [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0], [0.0, 0.0, 0.0, 0.0]],
            [[2.0, 2.0, 2.0, 2.0], [4.0, 4.0, 4.0, 4.0], [6.0, 6.0, 6.0, 6.0]],
        ],
        dtype=torch.float32,
    )
    # Mask: first item has 2 active tokens, second item has 3 active tokens
    mask = torch.tensor(
        [
            [1, 1, 0],
            [1, 1, 1],
        ],
        dtype=torch.long,
    )

    pooled = service._mean_pooling(hidden, mask)
    # Item 0 mean of [[1,2,3,4], [5,6,7,8]] = [3,4,5,6]
    assert torch.allclose(pooled[0], torch.tensor([3.0, 4.0, 5.0, 6.0]))
    # Item 1 mean of [[2,2,2,2], [4,4,4,4], [6,6,6,6]] = [4,4,4,4]
    assert torch.allclose(pooled[1], torch.tensor([4.0, 4.0, 4.0, 4.0]))

    # Normalized vectors must have L2 norm == 1.0
    normed = torch.nn.functional.normalize(pooled, p=2, dim=1)
    norms = torch.norm(normed, p=2, dim=1)
    assert torch.allclose(norms, torch.tensor([1.0, 1.0]))


def test_empty_input_handling():
    """Verify that empty document sequences return empty embedding lists."""
    service = EmbeddingService(settings=Settings())
    assert service.embed_documents([]) == []


def test_empty_query_raises():
    """Verify that an empty or whitespace query raises ValueError."""
    service = EmbeddingService(settings=Settings())
    with pytest.raises(ValueError, match="Query string must not be empty"):
        service.embed_query("")
    with pytest.raises(ValueError, match="Query string must not be empty"):
        service.embed_query("   ")


def test_batch_processing_and_output_dimensions():
    """Verify that batched embeddings produce exact 768-dimensional outputs."""
    mock_model = MagicMock()
    mock_tokenizer = MagicMock()

    # Mock tokenizer output
    mock_tokenizer.return_value = {
        "input_ids": torch.tensor([[1, 2, 3], [4, 5, 6]]),
        "attention_mask": torch.tensor([[1, 1, 1], [1, 1, 1]]),
    }

    # Mock model output: batch=2, seq=3, dim=768
    fake_hidden = torch.ones((2, 3, EXPECTED_EMBEDDING_DIM), dtype=torch.float32)
    mock_output = MagicMock()
    mock_output.last_hidden_state = fake_hidden
    mock_model.return_value = mock_output

    mock_mgr = MagicMock()
    mock_mgr.get_model_and_tokenizer.return_value = (mock_model, mock_tokenizer, "cpu")

    service = EmbeddingService(settings=Settings(), model_manager=mock_mgr)
    docs = [("Title A", "Chunk text 1"), ("Title B", "Chunk text 2")]

    vectors = service.embed_documents(docs, batch_size=2)
    assert len(vectors) == 2
    assert len(vectors[0]) == EXPECTED_EMBEDDING_DIM
    assert len(vectors[1]) == EXPECTED_EMBEDDING_DIM


def test_model_manager_cleanup():
    """Verify that model unload resets state and triggers garbage collection."""
    mgr = EmbeddingModelManager()
    mgr._model = "fake_model"
    mgr._tokenizer = "fake_tokenizer"
    mgr._current_key = ("model", "cpu")

    mgr.unload_model()
    assert mgr._model is None
    assert mgr._tokenizer is None
    assert mgr._current_key is None
