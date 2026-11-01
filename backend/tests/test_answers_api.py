"""API integration tests for grounded answer generation endpoint."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from lectra_backend.dependencies import get_generation_service
from lectra_backend.main import create_app
from lectra_core.config import Settings
from lectra_core.generation.exceptions import (
    GroqAuthError,
    GroqRateLimitError,
    GroqTimeoutError,
)
from lectra_core.generation.schemas import AnswerResponse, CitationItem


@pytest.fixture
def mock_gen_service():
    """Mock GenerationService dependency."""
    mock = MagicMock()
    return mock


@pytest.fixture
def api_client(tmp_path, mock_gen_service):
    """TestClient fixture with mocked generation dependency."""
    db_file = tmp_path / "test_answers_api.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file}",
        data_dir=tmp_path,
        environment="testing",
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_generation_service] = lambda: mock_gen_service

    with TestClient(app) as client:
        yield client, mock_gen_service


def test_generate_answer_endpoint_success(api_client):
    """Verify POST /api/v1/answers/generate returns 200 and structured response with citations."""
    client, mock_service = api_client

    sample_citation = CitationItem(
        source_id="S1",
        video_title="N meetings In One Room | Greedy Algorithm",
        youtube_id="II6ziNnub1Q",
        chunk_index=5,
        start_seconds=439.9,
        end_seconds=528.6,
        youtube_url="https://www.youtube.com/watch?v=II6ziNnub1Q&t=439",
    )
    mock_service.generate_answer.return_value = AnswerResponse(
        status="answered",
        answer="The meetings are sorted by finish time in ascending order [S1].",
        citations=[sample_citation],
    )

    req_body = {
        "query": "How do you select maximum non-overlapping meetings?",
        "top_k": 5,
        "score_threshold": None,
        "playlist_id": None,
    }
    response = client.post("/api/v1/answers/generate", json=req_body)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "answered"
    assert "finish time" in data["answer"]
    assert len(data["citations"]) == 1
    assert data["citations"][0]["source_id"] == "S1"
    assert data["citations"][0]["youtube_id"] == "II6ziNnub1Q"
    assert (
        data["citations"][0]["youtube_url"] == "https://www.youtube.com/watch?v=II6ziNnub1Q&t=439"
    )


def test_generate_answer_insufficient_context(api_client):
    """Verify 200 response with status insufficient_context and empty citations."""
    client, mock_service = api_client

    mock_service.generate_answer.return_value = AnswerResponse(
        status="insufficient_context",
        answer="The lecture transcript does not cover Dijkstra algorithm.",
        citations=[],
    )

    response = client.post(
        "/api/v1/answers/generate",
        json={"query": "How does Dijkstra algorithm work?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "insufficient_context"
    assert data["citations"] == []


def test_generate_answer_empty_query_returns_422(api_client):
    """Verify empty or whitespace query returns HTTP 422."""
    client, _ = api_client

    res1 = client.post("/api/v1/answers/generate", json={"query": ""})
    assert res1.status_code == 422

    res2 = client.post("/api/v1/answers/generate", json={"query": "    "})
    assert res2.status_code == 422


def test_generate_answer_rate_limit_returns_429(api_client):
    """Verify GroqRateLimitError translates to HTTP 429."""
    client, mock_service = api_client
    mock_service.generate_answer.side_effect = GroqRateLimitError("Rate limit reached")

    response = client.post(
        "/api/v1/answers/generate",
        json={"query": "Test query"},
    )
    assert response.status_code == 429
    assert "rate limit exceeded" in response.json()["detail"].lower()


def test_generate_answer_timeout_returns_504(api_client):
    """Verify GroqTimeoutError translates to HTTP 504."""
    client, mock_service = api_client
    mock_service.generate_answer.side_effect = GroqTimeoutError("Request timed out")

    response = client.post(
        "/api/v1/answers/generate",
        json={"query": "Test query"},
    )
    assert response.status_code == 504
    assert "timed out" in response.json()["detail"].lower()


def test_generate_answer_auth_error_returns_503(api_client):
    """Verify GroqAuthError translates to HTTP 503 without revealing secrets."""
    client, mock_service = api_client
    mock_service.generate_answer.side_effect = GroqAuthError("Invalid credentials")

    response = client.post(
        "/api/v1/answers/generate",
        json={"query": "Test query"},
    )
    assert response.status_code == 503
    assert "verify provider credentials" in response.json()["detail"].lower()


def test_generate_answer_passes_filters_to_service(api_client):
    """Verify metadata filters pass through to GenerationService correctly."""
    client, mock_service = api_client
    mock_service.generate_answer.return_value = AnswerResponse(
        status="answered",
        answer="Filtered answer.",
        citations=[],
    )

    req_body = {
        "query": "Activity selection",
        "top_k": 3,
        "score_threshold": 0.7,
        "youtube_id": "II6ziNnub1Q",
        "playlist_id": "pl-123",
    }
    res = client.post("/api/v1/answers/generate", json=req_body)
    assert res.status_code == 200

    mock_service.generate_answer.assert_called_once()
    passed_req = mock_service.generate_answer.call_args[0][0]
    assert passed_req.query == "Activity selection"
    assert passed_req.top_k == 3
    assert passed_req.score_threshold == 0.7
    assert passed_req.youtube_id == "II6ziNnub1Q"
    assert passed_req.playlist_id == "pl-123"
