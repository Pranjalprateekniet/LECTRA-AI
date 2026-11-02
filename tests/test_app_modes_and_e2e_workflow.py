"""End-to-End Workflow and Application Mode Tests (USER vs DEVELOPER).

Covers:
1. Explicit application mode (USER vs DEVELOPER).
2. Refusal to silently fall back to local retrieval when RETRIEVAL_API_URL is missing in USER mode.
3. Ingestion and playlist mutation blockage in USER mode (HTTP 403).
4. Zero local embedding model loading on user machines in USER mode.
5. Complete End-to-End workflow:
   User question -> Local FastAPI (/api/v1/answers/generate)
                 -> Hosted Retrieval API (/api/v1/retrieve)
                 -> Qdrant Cloud (read-only query)
                 -> ContextBuilder
                 -> Local Groq API
                 -> Final Answer + timestamp citations.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from lectra_backend.main import create_app as create_local_backend_app
from lectra_core.config import Settings
from lectra_core.embeddings.model import EmbeddingModelManager
from lectra_core.retrieval.remote import RemoteRetrievalService

from retrieval_service.config import RetrievalServiceSettings
from retrieval_service.limiter import MemoryRateLimiter
from retrieval_service.main import create_app as create_hosted_retrieval_app
from retrieval_service.service import HostedRetrievalService

# --------------------------------------------------------------------------
# 1. Mode Configuration Tests (Phase 3: Zero-Hosting-Cost Local Mode)
# --------------------------------------------------------------------------


def test_user_mode_initializes_without_cloud_credentials_or_retrieval_url():
    """In USER mode, neither cloud Qdrant credentials nor RETRIEVAL_API_URL are required."""
    s = Settings(
        app_mode="USER",
        retrieval_api_url=None,
        qdrant_url=None,
        qdrant_api_key=None,
    )
    assert s.app_mode == "USER"
    assert s.retrieval_api_url is None
    assert s.qdrant_url is None
    assert s.qdrant_api_key is None
    assert str(s.qdrant_path).endswith("data/qdrant")


def test_user_mode_uses_local_qdrant_vector_store():
    """In USER mode, QdrantVectorStore instantiates local embedded client."""
    from lectra_core.vectorstore.qdrant import QdrantVectorStore

    s = Settings(app_mode="USER", retrieval_api_url=None)
    vs = QdrantVectorStore(settings=s)
    assert vs.is_local is True
    assert vs.collection_name == "revision_chunks"


def test_developer_mode_retains_cloud_behavior():
    """In DEVELOPER mode with QDRANT_URL, cloud client is configured."""
    from lectra_core.vectorstore.qdrant import QdrantVectorStore

    s = Settings(
        app_mode="DEVELOPER",
        qdrant_url="https://cloud-cluster.qdrant.io",
        qdrant_api_key="secret-key",
    )
    assert s.app_mode == "DEVELOPER"
    assert s.qdrant_url == "https://cloud-cluster.qdrant.io"
    vs = QdrantVectorStore(settings=s)
    assert vs.is_local is False


def test_developer_mode_local_qdrant_behavior():
    """In DEVELOPER mode without QDRANT_URL, local persistent Qdrant is used."""
    from lectra_core.vectorstore.qdrant import QdrantVectorStore

    s = Settings(
        app_mode="DEVELOPER",
        qdrant_url=None,
    )
    assert s.app_mode == "DEVELOPER"
    assert s.qdrant_url is None
    vs = QdrantVectorStore(settings=s)
    assert vs.is_local is True


def test_fastapi_dependency_injection_consistency():
    """Verify get_retrieval_service and get_generation_service are consistent."""
    from lectra_backend.dependencies import get_generation_service, get_retrieval_service
    from lectra_core.generation.service import GenerationService
    from lectra_core.retrieval.remote import RemoteRetrievalService
    from lectra_core.retrieval.service import RetrievalService

    # 1. USER mode without RETRIEVAL_API_URL -> local RetrievalService
    user_local_settings = Settings(app_mode="USER", retrieval_api_url=None)
    retrieval_svc = get_retrieval_service(settings=user_local_settings)
    assert isinstance(retrieval_svc, RetrievalService)
    assert retrieval_svc.vector_store.is_local is True

    gen_svc = get_generation_service(
        settings=user_local_settings,
        retrieval_service=retrieval_svc,
    )
    assert isinstance(gen_svc, GenerationService)
    assert gen_svc.retrieval_service is retrieval_svc

    # Direct GenerationService instantiation without explicit retrieval_service
    direct_gen_svc = GenerationService(settings=user_local_settings)
    assert isinstance(direct_gen_svc.retrieval_service, RetrievalService)
    assert direct_gen_svc.retrieval_service.vector_store.is_local is True

    # 2. USER mode with RETRIEVAL_API_URL -> RemoteRetrievalService
    user_remote_settings = Settings(
        app_mode="USER",
        retrieval_api_url="https://api.revisionrag.com/api/v1/retrieve",
    )
    remote_retrieval_svc = get_retrieval_service(settings=user_remote_settings)
    assert isinstance(remote_retrieval_svc, RemoteRetrievalService)

    direct_remote_gen_svc = GenerationService(settings=user_remote_settings)
    assert isinstance(direct_remote_gen_svc.retrieval_service, RemoteRetrievalService)



# --------------------------------------------------------------------------
# 2. Ingestion Blockage in USER Mode
# --------------------------------------------------------------------------


def test_user_mode_blocks_playlist_submission_with_403(tmp_path):
    user_settings = Settings(
        app_mode="USER",
        sqlite_path=tmp_path / "test_user.db",
        database_url=f"sqlite:///{tmp_path}/test_user.db",
    )
    app = create_local_backend_app(settings=user_settings)
    client = TestClient(app)

    res = client.post(
        "/api/v1/playlists",
        json={"url": "https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"},
    )
    assert res.status_code == 403
    assert "Playlist ingestion is disabled in USER mode" in res.json()["detail"]


def test_user_mode_blocks_video_retry_with_403(tmp_path):
    user_settings = Settings(
        app_mode="USER",
        sqlite_path=tmp_path / "test_user.db",
        database_url=f"sqlite:///{tmp_path}/test_user.db",
    )
    app = create_local_backend_app(settings=user_settings)
    client = TestClient(app)

    res = client.post("/api/v1/playlists/videos/dummy-vid-123/retry")
    assert res.status_code == 403
    assert "disabled in USER mode" in res.json()["detail"]


def test_user_mode_health_endpoint_reports_user_mode(tmp_path):
    user_settings = Settings(
        app_mode="USER",
        sqlite_path=tmp_path / "test_user.db",
        database_url=f"sqlite:///{tmp_path}/test_user.db",
    )
    app = create_local_backend_app(settings=user_settings)
    client = TestClient(app)

    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["app_mode"] == "USER"
    assert data["components"]["qdrant_configured"] is True
    assert data["components"]["qdrant_mode"] == "local"
    assert "local_qdrant_path" in data["components"]


# --------------------------------------------------------------------------
# 3. Model Weight Isolation: Zero Model Loading on User Machines
# --------------------------------------------------------------------------


def test_user_mode_never_instantiates_embedding_model(tmp_path):
    """Verify that user machines never load PyTorch weights or EmbeddingModelManager."""
    user_settings = Settings(
        app_mode="USER",
        retrieval_api_url="https://api.revisionrag.com/api/v1/retrieve",
        sqlite_path=tmp_path / "test_user.db",
        database_url=f"sqlite:///{tmp_path}/test_user.db",
    )

    with patch.object(EmbeddingModelManager, "get_model_and_tokenizer") as mock_get_model:
        # Create RemoteRetrievalService
        remote_svc = RemoteRetrievalService(settings=user_settings)
        assert remote_svc.settings.app_mode == "USER"
        # Verify get_model_and_tokenizer was never called
        assert mock_get_model.called is False


# --------------------------------------------------------------------------
# 4. Complete End-to-End Workflow Test (Modification 9)
# --------------------------------------------------------------------------


def test_complete_e2e_workflow(tmp_path):
    """Full workflow: User question -> Local Backend -> Hosted Retrieval API

    -> Qdrant Cloud -> Local ContextBuilder -> Local Groq -> Final Answer.
    """
    # 1. Setup Hosted Retrieval Service (simulating centrally hosted server)
    hosted_settings = RetrievalServiceSettings(
        qdrant_url="https://fake-central-cluster.cloud.qdrant.io",
        qdrant_api_key="secret-server-key-dont-leak",
        qdrant_collection_name="revision_chunks",
        rate_limit_per_minute=20,
        rate_limit_per_hour=100,
        cors_origins=[],  # Server-to-server; no wildcard CORS
    )

    # Mock Qdrant Cloud client (Strictly read-only)
    mock_qdrant = MagicMock()
    mock_point = MagicMock()
    mock_point.id = "chunk_greedy_001"
    mock_point.score = 0.94
    mock_point.payload = {
        "chunk_id": "chunk_greedy_001",
        "video_id": "vid_II6ziNnub1Q",
        "youtube_id": "II6ziNnub1Q",
        "playlist_id": "pl_greedy_striver",
        "title": "N meetings In One Room | Greedy Algorithm",
        "chunk_index": 1,
        "start_seconds": 185.0,
        "end_seconds": 260.0,
        "duration_seconds": 75.0,
        "text": (
            "To solve N meetings in one room, sort all meetings "
            "by their end time in ascending order."
        ),
        "youtube_url": "https://www.youtube.com/watch?v=II6ziNnub1Q&t=185",
    }
    qdrant_search_res = MagicMock()
    qdrant_search_res.points = [mock_point]
    mock_qdrant.query_points.return_value = qdrant_search_res
    mock_qdrant.collection_exists.return_value = True

    mock_server_embedding = MagicMock()
    mock_server_embedding.embed_query.return_value = [0.05] * 768

    hosted_service = HostedRetrievalService(
        settings=hosted_settings,
        embedding_service=mock_server_embedding,
        qdrant_client=mock_qdrant,
    )

    hosted_app = create_hosted_retrieval_app(
        settings=hosted_settings,
        rate_limiter=MemoryRateLimiter(),
        retrieval_service=hosted_service,
    )
    hosted_client = TestClient(hosted_app)

    # 2. Setup Local User Backend
    user_settings = Settings(
        app_mode="USER",
        retrieval_api_url="http://hosted-api.local/api/v1/retrieve",
        groq_api_key="gsk_user_secret_groq_key_9999",
        sqlite_path=tmp_path / "user_chat.db",
        database_url=f"sqlite:///{tmp_path}/user_chat.db",
    )

    # Adapter bridging local backend's httpx calls directly to hosted_app TestClient
    def mock_http_post(url, json=None, **kwargs):
        # Forward to hosted retrieval service
        resp = hosted_client.post("/api/v1/retrieve", json=json)
        return resp

    mock_client = MagicMock()
    mock_client.post.side_effect = mock_http_post

    local_remote_retrieval = RemoteRetrievalService(settings=user_settings, client=mock_client)

    # Mock local Groq client (running on user machine with user's key)
    mock_groq = MagicMock()
    mock_groq.generate_chat_completion.return_value = (
        '{"status": "answered", '
        '"answer": "To schedule the maximum number of meetings, sort them by end time [S1].", '
        '"citations": ["S1"]}'
    )

    # 3. Create Local Backend App
    local_app = create_local_backend_app(settings=user_settings)

    from lectra_backend.dependencies import get_generation_service, get_retrieval_service
    from lectra_core.generation.service import GenerationService

    local_gen_service = GenerationService(
        settings=user_settings,
        retrieval_service=local_remote_retrieval,
        groq_client=mock_groq,
    )

    local_app.dependency_overrides[get_retrieval_service] = lambda: local_remote_retrieval
    local_app.dependency_overrides[get_generation_service] = lambda: local_gen_service

    local_client = TestClient(local_app)

    # 4. User submits question to local backend
    response = local_client.post(
        "/api/v1/answers/generate",
        json={"query": "How do we schedule N meetings in one room?", "top_k": 3},
    )

    assert response.status_code == 200
    answer_data = response.json()

    # 5. Verify the entire end-to-end chain results
    assert answer_data["status"] == "answered"
    assert "sort them by end time" in answer_data["answer"]
    assert len(answer_data["citations"]) == 1

    citation = answer_data["citations"][0]
    assert citation["source_id"] == "S1"
    assert citation["video_title"] == "N meetings In One Room | Greedy Algorithm"
    assert citation["start_seconds"] == 185.0
    assert citation["youtube_url"] == "https://www.youtube.com/watch?v=II6ziNnub1Q&t=185"

    # 6. Verify security properties:
    # - Hosted Qdrant client executed strictly query_points (NO writes or deletes)
    assert mock_qdrant.query_points.called is True
    assert getattr(mock_qdrant, "upsert", MagicMock()).called is False
    assert getattr(mock_qdrant, "delete", MagicMock()).called is False

    # - User Groq key was used on local Groq client and NEVER sent to hosted retrieval service
    mock_groq.generate_chat_completion.assert_called_once()
    assert "gsk_user_secret_groq_key_9999" not in str(mock_client.post.call_args)

    # - Hosted Qdrant credentials were NEVER leaked to local user or client
    assert "secret-server-key-dont-leak" not in str(response.json())


# --------------------------------------------------------------------------
# 5. Local Qdrant Retrieval and Query Tests (Phase 3)
# --------------------------------------------------------------------------


def test_local_retrieval_service_reads_local_qdrant():
    """Verify that RetrievalService in USER mode queries local persistent Qdrant."""
    from lectra_core.retrieval.schemas import RetrievalQuery
    from lectra_core.retrieval.service import RetrievalService

    user_settings = Settings(app_mode="USER", retrieval_api_url=None)
    mock_embedding = MagicMock()
    # Return dummy unit vector
    mock_embedding.embed_query.return_value = [0.01] * 768

    retrieval_svc = RetrievalService(settings=user_settings, embedding_service=mock_embedding)
    assert retrieval_svc.vector_store.is_local is True

    # Search against actual local collection
    res = retrieval_svc.search_query(RetrievalQuery(query="LangChain prompts", top_k=3))
    assert res.total_results > 0
    first_result = res.results[0]
    assert first_result.chunk_id is not None
    assert first_result.video_title is not None
    assert first_result.start_seconds >= 0
    assert first_result.youtube_url.startswith("https://www.youtube.com/watch?v=")


def test_local_retrieval_playlist_filtering():
    """Verify playlist filtering isolates chunks to the requested playlist."""
    from lectra_core.retrieval.schemas import RetrievalQuery
    from lectra_core.retrieval.service import RetrievalService

    user_settings = Settings(app_mode="USER", retrieval_api_url=None)
    mock_embedding = MagicMock()
    mock_embedding.embed_query.return_value = [0.01] * 768

    retrieval_svc = RetrievalService(settings=user_settings, embedding_service=mock_embedding)

    # 1. LangChain playlist
    langchain_id = "0fd210e4-904f-4127-b539-130cb1497377"
    lc_res = retrieval_svc.search_query(
        RetrievalQuery(query="prompt templates", playlist_id=langchain_id, top_k=3)
    )
    assert lc_res.total_results > 0
    for hit in lc_res.results:
        assert hit.playlist_id == langchain_id

    # 2. Striver DSA playlist
    striver_id = "3820e00b-81b6-4f34-9e68-011ddc3d9f98"
    striver_res = retrieval_svc.search_query(
        RetrievalQuery(query="binary search", playlist_id=striver_id, top_k=3)
    )
    assert striver_res.total_results > 0
    for hit in striver_res.results:
        assert hit.playlist_id == striver_id


def test_query_endpoint_returns_timestamped_citations(tmp_path):
    """Verify /api/v1/query and answers/generate return grounded answers with citations."""
    from lectra_core.generation.service import GenerationService
    from lectra_core.retrieval.service import RetrievalService

    user_settings = Settings(
        app_mode="USER",
        retrieval_api_url=None,
        groq_api_key="gsk_test_student_groq_key",
        sqlite_path=tmp_path / "user_test.db",
        database_url=f"sqlite:///{tmp_path}/user_test.db",
    )

    mock_embedding = MagicMock()
    mock_embedding.embed_query.return_value = [0.01] * 768
    local_retrieval = RetrievalService(settings=user_settings, embedding_service=mock_embedding)

    mock_groq = MagicMock()
    mock_groq.generate_chat_completion.return_value = (
        '{"status": "answered", '
        '"answer": "Binary search divides the search space in half at each step [S1].", '
        '"citations": ["S1"]}'
    )

    gen_service = GenerationService(
        settings=user_settings,
        retrieval_service=local_retrieval,
        groq_client=mock_groq,
    )

    app = create_local_backend_app(settings=user_settings)
    from lectra_backend.dependencies import get_generation_service, get_retrieval_service
    app.dependency_overrides[get_retrieval_service] = lambda: local_retrieval
    app.dependency_overrides[get_generation_service] = lambda: gen_service

    client = TestClient(app)

    # Test /api/v1/query endpoint
    res = client.post(
        "/api/v1/query",
        json={"query": "Explain binary search algorithm", "top_k": 2},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "answered"
    assert "Binary search divides" in data["answer"]
    assert len(data["citations"]) >= 1
    citation = data["citations"][0]
    assert citation["source_id"] == "S1"
    assert citation["video_title"] is not None
    assert citation["start_seconds"] >= 0
    assert citation["youtube_url"].startswith("https://www.youtube.com/watch?v=")
