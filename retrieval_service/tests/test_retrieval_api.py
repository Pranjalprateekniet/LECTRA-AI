"""Comprehensive tests for the hosted read-only retrieval API."""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from retrieval_service.config import RetrievalServiceSettings
from retrieval_service.limiter import MemoryRateLimiter
from retrieval_service.main import create_app
from retrieval_service.service import (
    HostedRetrievalService,
)


@pytest.fixture
def mock_embedding_service():
    svc = MagicMock()
    svc.embed_query.return_value = [0.1] * 768
    return svc


@pytest.fixture
def mock_qdrant_client():
    client = MagicMock()

    # Default mock points returned by query_points
    point1 = MagicMock()
    point1.id = "chunk_abc123"
    point1.score = 0.88
    point1.payload = {
        "chunk_id": "chunk_abc123",
        "video_id": "vid_xyz789",
        "youtube_id": "II6ziNnub1Q",
        "playlist_id": "pl_001",
        "title": "Fractional Knapsack Explained",
        "chunk_index": 2,
        "start_seconds": 120.0,
        "end_seconds": 195.0,
        "duration_seconds": 75.0,
        "text": "The greedy choice property applies directly to fractional knapsack.",
        "youtube_url": "https://www.youtube.com/watch?v=II6ziNnub1Q&t=120",
    }

    res = MagicMock()
    res.points = [point1]
    client.query_points.return_value = res
    client.collection_exists.return_value = True
    return client


@pytest.fixture
def test_settings():
    return RetrievalServiceSettings(
        qdrant_url="https://fake-cluster.cloud.qdrant.io",
        qdrant_api_key="secret-qdrant-key-12345",
        qdrant_collection_name="test_revision_chunks",
        rate_limit_per_minute=5,
        rate_limit_per_hour=20,
        max_query_length=1000,
        max_top_k=10,
        max_concurrent_requests=5,
        request_timeout_seconds=2.0,
        trusted_proxies=["127.0.0.1", "::1"],
        cors_origins=["*"],
    )


@pytest.fixture
def app_and_client(test_settings, mock_embedding_service, mock_qdrant_client):
    limiter = MemoryRateLimiter(
        rate_limit_per_minute=test_settings.rate_limit_per_minute,
        rate_limit_per_hour=test_settings.rate_limit_per_hour,
    )
    svc = HostedRetrievalService(
        settings=test_settings,
        embedding_service=mock_embedding_service,
        qdrant_client=mock_qdrant_client,
    )
    app = create_app(
        settings=test_settings,
        rate_limiter=limiter,
        retrieval_service=svc,
    )
    return app, TestClient(app), mock_qdrant_client, limiter


# 1. Valid retrieval request
def test_valid_retrieval_request(app_and_client):
    app, client, qdrant, _ = app_and_client

    response = client.post("/api/v1/retrieve", json={"query": "knapsack algorithm", "top_k": 3})
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert len(data["results"]) == 1
    chunk = data["results"][0]
    assert chunk["video_title"] == "Fractional Knapsack Explained"
    assert "greedy choice" in chunk["text"]
    assert chunk["start_timestamp"] == 120.0
    assert chunk["start_seconds"] == 120.0
    assert chunk["youtube_url"] == "https://www.youtube.com/watch?v=II6ziNnub1Q&t=120"
    assert chunk["score"] == 0.88
    assert chunk["similarity_score"] == 0.88

    # Rate limit headers check
    assert "X-RateLimit-Limit-Minute" in response.headers
    assert "X-RateLimit-Remaining-Minute" in response.headers


# 2. Empty retrieval results
def test_empty_retrieval_results(app_and_client):
    app, client, qdrant, _ = app_and_client
    res = MagicMock()
    res.points = []
    qdrant.query_points.return_value = res

    response = client.post("/api/v1/retrieve", json={"query": "quantum gravity"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["results"] == []


# 3. Invalid request body
def test_invalid_request_body_empty_query(app_and_client):
    _, client, _, _ = app_and_client
    # Empty query string
    response = client.post("/api/v1/retrieve", json={"query": "   "})
    assert response.status_code == 400


def test_invalid_request_body_missing_query(app_and_client):
    _, client, _, _ = app_and_client
    # Missing required query field
    response = client.post("/api/v1/retrieve", json={"top_k": 5})
    assert response.status_code == 400


def test_invalid_request_forbidden_extra_fields(app_and_client):
    _, client, _, _ = app_and_client
    # Client tries to pass arbitrary database/collection/filter fields
    response = client.post(
        "/api/v1/retrieve",
        json={"query": "valid query", "collection_name": "other_collection", "delete_all": True},
    )
    assert response.status_code == 400


# 4. Excessively long query (>1000 characters)
def test_excessively_long_query_rejected(app_and_client):
    _, client, _, _ = app_and_client
    long_query = "x" * 1001
    response = client.post("/api/v1/retrieve", json={"query": long_query})
    assert response.status_code == 400


# 5. Top-k above the allowed maximum (>10)
def test_top_k_above_maximum_rejected(app_and_client):
    _, client, _, _ = app_and_client
    response = client.post("/api/v1/retrieve", json={"query": "valid query", "top_k": 11})
    assert response.status_code == 400

    response2 = client.post("/api/v1/retrieve", json={"query": "valid query", "top_k": 0})
    assert response2.status_code == 400


# 6. Rate-limit enforcement (HTTP 429)
def test_rate_limit_enforcement_returns_429(app_and_client):
    _, client, _, limiter = app_and_client
    limiter.reset()

    # Limit is 5 per minute in test_settings
    for i in range(5):
        res = client.post("/api/v1/retrieve", json={"query": f"question {i}"})
        assert res.status_code == 200

    # 6th request from same IP must be rejected with 429
    res_exceeded = client.post("/api/v1/retrieve", json={"query": "question 6"})
    assert res_exceeded.status_code == 429
    assert "Retry-After" in res_exceeded.headers
    assert "Rate limit exceeded" in res_exceeded.json()["detail"]


# 7. Qdrant unavailable (returns 503 without exposing secrets)
def test_qdrant_unavailable_returns_503(app_and_client):
    app, client, qdrant, _ = app_and_client
    qdrant.query_points.side_effect = Exception(
        "ConnectionRefusedError: Failed to connect to Qdrant Cloud"
    )

    response = client.post("/api/v1/retrieve", json={"query": "test query"})
    assert response.status_code == 503
    body_text = response.text
    # Must NOT leak secret keys or cluster URLs
    assert "secret-qdrant-key" not in body_text
    assert "fake-cluster.cloud.qdrant.io" not in body_text
    assert "Knowledge base vector store is currently unavailable" in response.json()["detail"]


# 8. Request timeout (returns 504)
def test_request_timeout_returns_504(test_settings, mock_embedding_service, mock_qdrant_client):
    # Short timeout
    test_settings.request_timeout_seconds = 0.05
    svc = HostedRetrievalService(
        settings=test_settings,
        embedding_service=mock_embedding_service,
        qdrant_client=mock_qdrant_client,
    )

    # Simulate slow query without calling patched retrieve
    def slow_retrieve(query, top_k):
        time.sleep(0.15)
        from retrieval_service.schemas import RetrieveResponse
        return RetrieveResponse(success=True, results=[])

    with patch.object(svc, "retrieve", side_effect=slow_retrieve):
        app = create_app(
            settings=test_settings,
            rate_limiter=MemoryRateLimiter(),
            retrieval_service=svc,
        )
        client = TestClient(app)
        response = client.post("/api/v1/retrieve", json={"query": "timeout test"})
        assert response.status_code == 504
        assert "timed out" in response.json()["detail"]


# 9. Concurrency limit protection
def test_concurrency_limit_protection(test_settings, mock_embedding_service, mock_qdrant_client):
    test_settings.max_concurrent_requests = 1
    svc = HostedRetrievalService(
        settings=test_settings,
        embedding_service=mock_embedding_service,
        qdrant_client=mock_qdrant_client,
    )
    app = create_app(
        settings=test_settings,
        rate_limiter=MemoryRateLimiter(),
        retrieval_service=svc,
    )
    client = TestClient(app)

    # Acquire the single semaphore slot manually
    asyncio.run(app.state.concurrency_semaphore.acquire())

    try:
        # Request should fail with 503 capacity saturated
        res = client.post("/api/v1/retrieve", json={"query": "concurrent query"})
        assert res.status_code == 503
        assert "capacity" in res.json()["detail"].lower()
    finally:
        app.state.concurrency_semaphore.release()


# 10. Confirmation that write operations and admin endpoints are not publicly exposed
def test_write_and_admin_endpoints_not_exposed(app_and_client):
    _, client, _, _ = app_and_client

    unauthorized_endpoints = [
        ("POST", "/api/v1/collections"),
        ("DELETE", "/api/v1/collections/revision_chunks"),
        ("POST", "/api/v1/vectors/upsert"),
        ("DELETE", "/api/v1/vectors/delete"),
        ("POST", "/api/v1/playlists"),
        ("POST", "/api/v1/jobs"),
        ("GET", "/api/v1/playlists"),
        ("GET", "/api/v1/export"),
        ("POST", "/api/v1/ingest"),
    ]

    for method, path in unauthorized_endpoints:
        res = client.request(method, path)
        # Must return 404 Not Found or 405 Method Not Allowed; never 200 or 500
        assert res.status_code in (404, 405), f"Endpoint {method} {path} should not exist!"


# 11. Confirmation that Qdrant credentials are never returned
def test_qdrant_credentials_never_returned(app_and_client):
    _, client, _, _ = app_and_client

    # Probe /health
    res_health = client.get("/health")
    assert res_health.status_code == 200
    health_text = res_health.text
    assert "secret-qdrant-key" not in health_text
    assert "fake-cluster" not in health_text

    # Probe root /
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "secret-qdrant-key" not in res_root.text

    # Probe /api/v1/retrieve
    res_retrieve = client.post("/api/v1/retrieve", json={"query": "check secrets"})
    assert res_retrieve.status_code == 200
    assert "secret-qdrant-key" not in res_retrieve.text


# 12. Confirmation that the existing collection is not modified
def test_existing_collection_never_modified(app_and_client):
    _, client, qdrant, _ = app_and_client

    client.post("/api/v1/retrieve", json={"query": "verify read only", "top_k": 2})

    # Assert only query_points was called; no mutations
    assert qdrant.query_points.called is True
    assert getattr(qdrant, "upsert", MagicMock()).called is False
    assert getattr(qdrant, "delete", MagicMock()).called is False
    assert getattr(qdrant, "create_collection", MagicMock()).called is False
    assert getattr(qdrant, "delete_collection", MagicMock()).called is False


# 13. Health check probe failure handling
def test_health_check_degraded_when_qdrant_fails(app_and_client):
    _, client, qdrant, _ = app_and_client
    qdrant.collection_exists.return_value = False

    res = client.get("/health")
    assert res.status_code == 503
    data = res.json()
    assert data["status"] == "degraded"
    assert data["qdrant_status"] == "collection_not_found"
    assert "secret-qdrant-key" not in res.text
