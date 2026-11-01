"""API integration tests for semantic retrieval endpoint."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from lectra_backend.dependencies import get_retrieval_service
from lectra_backend.main import create_app
from lectra_core.config import Settings
from lectra_core.retrieval.schemas import SearchResponse, SearchResultItem
from lectra_core.retrieval.service import RetrievalError


@pytest.fixture
def mock_retrieval_service():
    """Mock RetrievalService instance for endpoint testing."""
    mock = MagicMock()
    return mock


@pytest.fixture
def api_client(tmp_path, mock_retrieval_service):
    """TestClient fixture with mocked retrieval dependency."""
    db_file = tmp_path / "test_retrieval_api.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file}",
        data_dir=tmp_path,
        environment="testing",
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_retrieval_service] = lambda: mock_retrieval_service

    with TestClient(app) as client:
        yield client, mock_retrieval_service


def test_search_endpoint_success(api_client):
    """Verify POST /api/v1/retrieval/search returns 200 and schema payload."""
    client, mock_service = api_client

    sample_result = SearchResultItem(
        chunk_id="chk-123",
        video_id="vid-456",
        youtube_id="II6ziNnub1Q",
        playlist_id="pl-789",
        video_title="N meetings In One Room",
        chunk_index=2,
        text="Sample chunk transcript content.",
        start_seconds=120.0,
        end_seconds=195.0,
        duration_seconds=75.0,
        similarity_score=0.825,
        youtube_url="https://www.youtube.com/watch?v=II6ziNnub1Q&t=120",
    )
    mock_service.search_query.return_value = SearchResponse(
        query="How do I sort meetings?",
        results=[sample_result],
        total_results=1,
    )

    req_body = {
        "query": "How do I sort meetings?",
        "top_k": 5,
        "score_threshold": None,
        "playlist_id": None,
        "video_id": None,
        "youtube_id": None,
    }
    response = client.post("/api/v1/retrieval/search", json=req_body)
    assert response.status_code == 200

    data = response.json()
    assert data["query"] == "How do I sort meetings?"
    assert data["total_results"] == 1
    assert len(data["results"]) == 1
    assert data["results"][0]["youtube_id"] == "II6ziNnub1Q"
    assert data["results"][0]["video_title"] == "N meetings In One Room"
    assert data["results"][0]["similarity_score"] == 0.825
    assert data["results"][0]["youtube_url"] == "https://www.youtube.com/watch?v=II6ziNnub1Q&t=120"


def test_search_endpoint_empty_query_rejected(api_client):
    """Verify empty query string is rejected with HTTP 422."""
    client, _ = api_client

    # Empty string
    res = client.post("/api/v1/retrieval/search", json={"query": ""})
    assert res.status_code == 422

    # Whitespace only
    res2 = client.post("/api/v1/retrieval/search", json={"query": "   "})
    assert res2.status_code == 422


def test_search_endpoint_invalid_top_k(api_client):
    """Verify top_k < 1 or > 100 returns HTTP 422."""
    client, _ = api_client

    res1 = client.post("/api/v1/retrieval/search", json={"query": "test", "top_k": 0})
    assert res1.status_code == 422

    res2 = client.post("/api/v1/retrieval/search", json={"query": "test", "top_k": 105})
    assert res2.status_code == 422


def test_search_endpoint_with_filters(api_client):
    """Verify optional filters pass through correctly into search_query call."""
    client, mock_service = api_client

    mock_service.search_query.return_value = SearchResponse(
        query="Train platforms",
        results=[],
        total_results=0,
    )

    req_body = {
        "query": "Train platforms",
        "top_k": 3,
        "youtube_id": "dxVcMDI7vyI",
    }
    res = client.post("/api/v1/retrieval/search", json=req_body)
    assert res.status_code == 200

    mock_service.search_query.assert_called_once()
    passed_query = mock_service.search_query.call_args[0][0]
    assert passed_query.query == "Train platforms"
    assert passed_query.top_k == 3
    assert passed_query.youtube_id == "dxVcMDI7vyI"


def test_search_endpoint_backend_failure_returns_503(api_client):
    """Verify that backend RetrievalError results in 503 without leaking secrets."""
    client, mock_service = api_client

    mock_service.search_query.side_effect = RetrievalError("Qdrant connection dropped")

    res = client.post(
        "/api/v1/retrieval/search",
        json={"query": "Knapsack capacity"},
    )
    assert res.status_code == 503
    data = res.json()
    assert "Retrieval service currently unavailable" in data["detail"]
