"""Unit tests for RetrievalService with mocked vector store and embeddings."""

from unittest.mock import MagicMock

import pytest
from lectra_core.config import Settings
from lectra_core.retrieval.schemas import RetrievalQuery
from lectra_core.retrieval.service import RetrievalError, RetrievalService


@pytest.fixture
def mock_embedding_service():
    """Mock EmbeddingService returning a deterministic 768-d vector."""
    mock = MagicMock()
    mock.embed_query.return_value = [0.1] * 768
    return mock


@pytest.fixture
def mock_vector_store():
    """Mock QdrantVectorStore with configurable query_points responses."""
    mock = MagicMock()
    mock.collection_name = "test_revision_chunks"
    return mock


def test_empty_query_raises_validation_error(mock_embedding_service, mock_vector_store):
    """Verify that empty or whitespace query strings are rejected."""
    service = RetrievalService(
        settings=Settings(),
        embedding_service=mock_embedding_service,
        vector_store=mock_vector_store,
    )
    with pytest.raises(ValueError, match="must not be empty"):
        service.search("")

    with pytest.raises(ValueError, match="must not be empty"):
        service.search("    ")


def test_invalid_parameters_raise_validation_error(mock_embedding_service, mock_vector_store):
    """Verify top_k bounds and score_threshold range checks."""
    service = RetrievalService(
        settings=Settings(),
        embedding_service=mock_embedding_service,
        vector_store=mock_vector_store,
    )
    with pytest.raises(ValueError, match="top_k must be at least 1"):
        service.search("valid query", top_k=0)

    with pytest.raises(ValueError, match="top_k must not exceed 100"):
        service.search("valid query", top_k=101)

    with pytest.raises(ValueError, match="score_threshold must be between"):
        service.search("valid query", score_threshold=-0.1)

    with pytest.raises(ValueError, match="score_threshold must be between"):
        service.search("valid query", score_threshold=1.5)


def test_successful_search_and_citation_generation(mock_embedding_service, mock_vector_store):
    """Verify end-to-end query processing, embedding invocation, and citation URL construction."""
    # Setup mock Qdrant hit
    mock_point = MagicMock()
    mock_point.id = "chunk-uuid-1"
    mock_point.score = 0.8543
    mock_point.payload = {
        "chunk_id": "chunk-uuid-1",
        "video_id": "video-uuid-1",
        "youtube_id": "II6ziNnub1Q",
        "playlist_id": "pl-uuid-1",
        "title": "N meetings In One Room",
        "chunk_index": 3,
        "start_seconds": 125.7,
        "end_seconds": 210.3,
        "duration_seconds": 84.6,
        "text": "Sort the meetings by end time in ascending order.",
    }

    mock_res = MagicMock()
    mock_res.points = [mock_point]
    mock_vector_store.client.query_points.return_value = mock_res

    service = RetrievalService(
        settings=Settings(),
        embedding_service=mock_embedding_service,
        vector_store=mock_vector_store,
    )

    resp = service.search(
        query="  How do I sort meetings?  ",
        top_k=3,
        score_threshold=0.5,
        youtube_id="II6ziNnub1Q",
    )

    # 1. Embedding was invoked with trimmed query
    mock_embedding_service.embed_query.assert_called_once_with("How do I sort meetings?")

    # 2. Qdrant client query_points was called with correct arguments
    mock_vector_store.client.query_points.assert_called_once()
    _, kwargs = mock_vector_store.client.query_points.call_args
    assert kwargs["collection_name"] == "test_revision_chunks"
    assert kwargs["limit"] == 3
    assert kwargs["score_threshold"] == 0.5
    assert kwargs["query_filter"] is not None
    assert kwargs["query_filter"].must[0].key == "youtube_id"
    assert kwargs["query_filter"].must[0].match.value == "II6ziNnub1Q"

    # 3. Response is properly populated and sorted
    assert resp.query == "How do I sort meetings?"
    assert resp.total_results == 1
    item = resp.results[0]
    assert item.chunk_id == "chunk-uuid-1"
    assert item.video_title == "N meetings In One Room"
    assert item.similarity_score == 0.8543
    # Timestamp URL must be floor/int seconds: 125.7 -> 125
    assert item.youtube_url == "https://www.youtube.com/watch?v=II6ziNnub1Q&t=125"


def test_empty_results_handling(mock_embedding_service, mock_vector_store):
    """Verify empty list returned when no points meet the criteria."""
    mock_res = MagicMock()
    mock_res.points = []
    mock_vector_store.client.query_points.return_value = mock_res

    service = RetrievalService(
        settings=Settings(),
        embedding_service=mock_embedding_service,
        vector_store=mock_vector_store,
    )

    resp = service.search("Unmatched query", top_k=5)
    assert resp.query == "Unmatched query"
    assert resp.results == []
    assert resp.total_results == 0


def test_malformed_payload_handling_safely(mock_embedding_service, mock_vector_store):
    """Verify points with missing text are skipped and missing youtube_id skips URL."""
    # Point 1: Missing text -> should be skipped
    p_no_text = MagicMock()
    p_no_text.id = "bad-chunk-1"
    p_no_text.score = 0.9
    p_no_text.payload = {"youtube_id": "vid1", "title": "No text"}

    # Point 2: Missing youtube_id -> URL should be empty string, not fabricated
    p_no_yt = MagicMock()
    p_no_yt.id = "chunk-2"
    p_no_yt.score = 0.75
    p_no_yt.payload = {
        "chunk_id": "chunk-2",
        "video_id": "v2",
        "youtube_id": None,
        "playlist_id": "p1",
        "title": "Missing YouTube ID",
        "text": "Valid chunk content here.",
        "start_seconds": 50.0,
        "end_seconds": 100.0,
    }

    mock_res = MagicMock()
    mock_res.points = [p_no_text, p_no_yt]
    mock_vector_store.client.query_points.return_value = mock_res

    service = RetrievalService(
        settings=Settings(),
        embedding_service=mock_embedding_service,
        vector_store=mock_vector_store,
    )

    resp = service.search("Test query")
    assert resp.total_results == 1
    valid_item = resp.results[0]
    assert valid_item.chunk_id == "chunk-2"
    assert valid_item.youtube_url == ""
    assert valid_item.text == "Valid chunk content here."


def test_search_query_schema_delegation(mock_embedding_service, mock_vector_store):
    """Verify search_query method delegates correctly from RetrievalQuery model."""
    mock_res = MagicMock()
    mock_res.points = []
    mock_vector_store.client.query_points.return_value = mock_res

    service = RetrievalService(
        settings=Settings(),
        embedding_service=mock_embedding_service,
        vector_store=mock_vector_store,
    )

    query_obj = RetrievalQuery(
        query="Greedy fractional knapsack",
        top_k=10,
        score_threshold=0.3,
        playlist_id="pl-test",
    )
    resp = service.search_query(query_obj)
    assert resp.query == "Greedy fractional knapsack"
    assert resp.total_results == 0


def test_backend_qdrant_failure_raises_retrieval_error(mock_embedding_service, mock_vector_store):
    """Verify backend search exceptions are caught and re-raised as RetrievalError."""
    mock_vector_store.client.query_points.side_effect = RuntimeError("Connection timed out")

    service = RetrievalService(
        settings=Settings(),
        embedding_service=mock_embedding_service,
        vector_store=mock_vector_store,
    )

    with pytest.raises(RetrievalError, match="Vector store search failed"):
        service.search("Failing query")
