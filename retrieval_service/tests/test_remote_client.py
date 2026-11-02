"""Tests for RemoteRetrievalService and local GenerationService integration."""

from unittest.mock import MagicMock

import httpx
import pytest
from lectra_core.config import Settings
from lectra_core.generation.schemas import GenerationRequest
from lectra_core.generation.service import GenerationService
from lectra_core.retrieval.remote import RemoteRetrievalService
from lectra_core.retrieval.service import RetrievalError


def test_remote_retrieval_service_success():
    mock_http = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "success": True,
        "results": [
            {
                "chunk_id": "chunk-101",
                "video_id": "vid-202",
                "youtube_id": "II6ziNnub1Q",
                "playlist_id": "pl-303",
                "video_title": "N meetings In One Room",
                "chunk_index": 0,
                "text": "Sort the meetings by ending time.",
                "start_timestamp": 45.0,
                "start_seconds": 45.0,
                "end_seconds": 120.0,
                "duration_seconds": 75.0,
                "score": 0.92,
                "similarity_score": 0.92,
                "youtube_url": "https://www.youtube.com/watch?v=II6ziNnub1Q&t=45",
            }
        ],
    }
    mock_http.post.return_value = mock_response

    settings = Settings(retrieval_api_url="https://api.revisionrag.com/api/v1/retrieve")
    remote_svc = RemoteRetrievalService(settings=settings, client=mock_http)

    res = remote_svc.search(query="how to sort meetings", top_k=3)
    assert res.total_results == 1
    chunk = res.results[0]
    assert chunk.video_title == "N meetings In One Room"
    assert chunk.start_seconds == 45.0
    assert chunk.similarity_score == 0.92
    assert chunk.youtube_url == "https://www.youtube.com/watch?v=II6ziNnub1Q&t=45"

    # Verify what payload was sent: strictly query and top_k; NO keys!
    mock_http.post.assert_called_once()
    call_args = mock_http.post.call_args
    sent_url = call_args[0][0]
    sent_payload = call_args[1]["json"]
    assert sent_url == "https://api.revisionrag.com/api/v1/retrieve"
    assert sent_payload == {"query": "how to sort meetings", "top_k": 3}
    assert "groq_api_key" not in sent_payload
    assert "qdrant_api_key" not in sent_payload


def test_remote_retrieval_service_rate_limited():
    mock_http = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "30"}
    mock_http.post.return_value = mock_response

    settings = Settings(retrieval_api_url="https://api.revisionrag.com")
    remote_svc = RemoteRetrievalService(settings=settings, client=mock_http)

    with pytest.raises(RetrievalError) as exc_info:
        remote_svc.search(query="knapsack problem")
    assert "rate limit reached" in str(exc_info.value).lower()
    assert "30 seconds" in str(exc_info.value)


def test_remote_retrieval_service_network_timeout():
    mock_http = MagicMock()
    mock_http.post.side_effect = httpx.TimeoutException("Connection timed out")

    settings = Settings(retrieval_api_url="https://api.revisionrag.com")
    remote_svc = RemoteRetrievalService(settings=settings, client=mock_http)

    with pytest.raises(RetrievalError) as exc_info:
        remote_svc.search(query="knapsack problem")
    assert "timed out" in str(exc_info.value).lower()


def test_generation_service_end_to_end_with_remote_retrieval():
    mock_http = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "success": True,
        "results": [
            {
                "chunk_id": "chunk-101",
                "video_id": "vid-202",
                "youtube_id": "II6ziNnub1Q",
                "playlist_id": "pl-303",
                "video_title": "N meetings In One Room",
                "chunk_index": 0,
                "text": "Sort the meetings by ending time to maximize count.",
                "start_timestamp": 45.0,
                "start_seconds": 45.0,
                "end_seconds": 120.0,
                "duration_seconds": 75.0,
                "score": 0.95,
                "similarity_score": 0.95,
                "youtube_url": "https://www.youtube.com/watch?v=II6ziNnub1Q&t=45",
            }
        ],
    }
    mock_http.post.return_value = mock_response

    settings = Settings(
        retrieval_api_url="https://api.revisionrag.com",
        groq_api_key="gsk-fake-user-groq-key",
    )
    remote_retrieval = RemoteRetrievalService(settings=settings, client=mock_http)

    mock_groq = MagicMock()
    mock_groq.generate_chat_completion.return_value = (
        '{"status": "answered", "answer": '
        '"To schedule meetings, sort them by ending time [S1].", "citations": ["S1"]}'
    )

    gen_svc = GenerationService(
        settings=settings,
        retrieval_service=remote_retrieval,
        groq_client=mock_groq,
    )

    req = GenerationRequest(query="How do we solve N meetings in one room?", top_k=3)
    answer = gen_svc.generate_answer(req)

    assert answer.status == "answered"
    assert "sort them by ending time" in answer.answer
    assert len(answer.citations) == 1
    cit = answer.citations[0]
    assert cit.source_id == "S1"
    assert cit.video_title == "N meetings In One Room"
    assert cit.start_seconds == 45.0
    assert cit.youtube_url == "https://www.youtube.com/watch?v=II6ziNnub1Q&t=45"

    # Confirm user's Groq key was used on local Groq client
    mock_groq.generate_chat_completion.assert_called_once()
    # Confirm retrieval call did NOT send the Groq key
    sent_payload = mock_http.post.call_args[1]["json"]
    assert "gsk-fake-user-groq-key" not in str(sent_payload)
