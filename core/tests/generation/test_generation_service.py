"""Unit tests for GenerationService pipeline, citation synthesis, and error handling."""

from unittest.mock import MagicMock

import pytest
from lectra_core.config import Settings
from lectra_core.generation.exceptions import GenerationError
from lectra_core.generation.schemas import GenerationRequest
from lectra_core.generation.service import GenerationService
from lectra_core.retrieval.schemas import SearchResponse, SearchResultItem


def make_sample_chunk(
    chunk_id: str = "chk-1",
    title: str = "N meetings In One Room",
    yt_id: str = "II6ziNnub1Q",
    idx: int = 5,
    start: float = 439.9,
    end: float = 528.6,
    text: str = "Sort the meetings by finish time in ascending order.",
) -> SearchResultItem:
    return SearchResultItem(
        chunk_id=chunk_id,
        video_id="vid-1",
        youtube_id=yt_id,
        playlist_id="pl-1",
        video_title=title,
        chunk_index=idx,
        text=text,
        start_seconds=start,
        end_seconds=end,
        duration_seconds=end - start,
        similarity_score=0.88,
        youtube_url=f"https://www.youtube.com/watch?v={yt_id}&t={int(start)}",
    )


@pytest.fixture
def mock_retrieval_service():
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_groq_client():
    mock = MagicMock()
    return mock


def test_generation_successful_answered(mock_retrieval_service, mock_groq_client):
    """Verify full end-to-end pipeline with grounded answer and citation metadata synthesis."""
    chunk = make_sample_chunk()
    mock_retrieval_service.search.return_value = SearchResponse(
        query="How to sort meetings?",
        results=[chunk],
        total_results=1,
    )
    mock_groq_client.generate_chat_completion.return_value = (
        '{"status": "answered", "answer": "You sort meetings by finish time [S1].", '
        '"citations": ["S1"]}'
    )

    service = GenerationService(
        settings=Settings(),
        retrieval_service=mock_retrieval_service,
        groq_client=mock_groq_client,
    )

    req = GenerationRequest(query="How to sort meetings?")
    resp = service.generate_answer(req)

    assert resp.status == "answered"
    assert "You sort meetings by finish time [S1]." in resp.answer
    assert len(resp.citations) == 1

    citation = resp.citations[0]
    assert citation.source_id == "S1"
    assert citation.video_title == "N meetings In One Room"
    assert citation.youtube_id == "II6ziNnub1Q"
    assert citation.chunk_index == 5
    assert citation.start_seconds == 439.9
    assert citation.youtube_url == "https://www.youtube.com/watch?v=II6ziNnub1Q&t=439"


def test_generation_insufficient_context_on_zero_retrieval(
    mock_retrieval_service, mock_groq_client
):
    """Verify early exit with insufficient_context when retrieval finds no chunks."""
    mock_retrieval_service.search.return_value = SearchResponse(
        query="Unknown query",
        results=[],
        total_results=0,
    )

    service = GenerationService(
        settings=Settings(),
        retrieval_service=mock_retrieval_service,
        groq_client=mock_groq_client,
    )

    req = GenerationRequest(query="What is Dijkstra algorithm?")
    resp = service.generate_answer(req)

    assert resp.status == "insufficient_context"
    assert resp.citations == []
    # Groq should not be invoked when retrieval returns 0 chunks
    mock_groq_client.generate_chat_completion.assert_not_called()


def test_generation_insufficient_context_from_llm(mock_retrieval_service, mock_groq_client):
    """Verify LLM returning insufficient_context clears citations and passes status."""
    chunk = make_sample_chunk()
    mock_retrieval_service.search.return_value = SearchResponse(
        query="Out of domain",
        results=[chunk],
        total_results=1,
    )
    mock_groq_client.generate_chat_completion.return_value = (
        '{"status": "insufficient_context", "answer": "The lecture does not cover Dijkstra.", '
        '"citations": []}'
    )

    service = GenerationService(
        settings=Settings(),
        retrieval_service=mock_retrieval_service,
        groq_client=mock_groq_client,
    )

    req = GenerationRequest(query="How does Dijkstra algorithm work?")
    resp = service.generate_answer(req)

    assert resp.status == "insufficient_context"
    assert resp.citations == []
    assert "does not cover" in resp.answer


def test_generation_rejects_unknown_citation_ids(mock_retrieval_service, mock_groq_client):
    """Verify hallucinated/unknown citation references (e.g. S99) are rejected."""
    chunk = make_sample_chunk()  # This will be assigned S1
    mock_retrieval_service.search.return_value = SearchResponse(
        query="Test query",
        results=[chunk],
        total_results=1,
    )
    # Model cites S1 and invented S99
    mock_groq_client.generate_chat_completion.return_value = (
        '{"status": "answered", "answer": "Answer text [S1] and [S99].", '
        '"citations": ["S1", "S99"]}'
    )

    service = GenerationService(
        settings=Settings(),
        retrieval_service=mock_retrieval_service,
        groq_client=mock_groq_client,
    )

    resp = service.generate_answer(GenerationRequest(query="Test query"))
    # Only S1 should be in citations, S99 rejected
    assert len(resp.citations) == 1
    assert resp.citations[0].source_id == "S1"


def test_generation_strips_markdown_code_fences(mock_retrieval_service, mock_groq_client):
    """Verify markdown code fence wrappers are stripped during JSON extraction."""
    chunk = make_sample_chunk()
    mock_retrieval_service.search.return_value = SearchResponse(
        query="Test query",
        results=[chunk],
        total_results=1,
    )
    mock_groq_client.generate_chat_completion.return_value = (
        '```json\n{"status": "partially_answered", "answer": "Partial info.", "citations": []}\n```'
    )

    service = GenerationService(
        settings=Settings(),
        retrieval_service=mock_retrieval_service,
        groq_client=mock_groq_client,
    )

    resp = service.generate_answer(GenerationRequest(query="Test query"))
    assert resp.status == "partially_answered"
    assert resp.answer == "Partial info."


def test_generation_invalid_json_raises_generation_error(mock_retrieval_service, mock_groq_client):
    """Verify non-JSON response from LLM raises GenerationError."""
    chunk = make_sample_chunk()
    mock_retrieval_service.search.return_value = SearchResponse(
        query="Test query",
        results=[chunk],
        total_results=1,
    )
    mock_groq_client.generate_chat_completion.return_value = "This is not JSON at all."

    service = GenerationService(
        settings=Settings(),
        retrieval_service=mock_retrieval_service,
        groq_client=mock_groq_client,
    )

    with pytest.raises(GenerationError, match="did not contain valid JSON"):
        service.generate_answer(GenerationRequest(query="Test query"))


def test_generation_service_defaults_to_local_retrieval_in_user_mode(mock_groq_client, tmp_path):
    """Verify GenerationService defaults to local RetrievalService in USER mode."""
    from lectra_core.retrieval.service import RetrievalService

    user_settings = Settings(
        app_mode="USER",
        retrieval_api_url=None,
        qdrant_path=tmp_path / "qdrant",
        sqlite_path=tmp_path / "user.db",
        database_url=f"sqlite:///{tmp_path}/user.db",
    )
    service = GenerationService(settings=user_settings, groq_client=mock_groq_client)
    assert isinstance(service.retrieval_service, RetrievalService)
    assert service.retrieval_service.vector_store.is_local is True


def test_generation_service_selects_remote_retrieval_when_url_set(mock_groq_client, tmp_path):
    """Verify GenerationService selects RemoteRetrievalService when retrieval_api_url is set."""
    from lectra_core.retrieval.remote import RemoteRetrievalService

    user_settings = Settings(
        app_mode="USER",
        retrieval_api_url="https://retrieval.example.com/api/v1/retrieve",
        sqlite_path=tmp_path / "user.db",
        database_url=f"sqlite:///{tmp_path}/user.db",
    )
    service = GenerationService(settings=user_settings, groq_client=mock_groq_client)
    assert isinstance(service.retrieval_service, RemoteRetrievalService)
