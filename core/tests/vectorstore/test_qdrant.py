"""Unit tests for Qdrant vector store and indexing service."""

import uuid
from unittest.mock import MagicMock

import pytest
from lectra_core.config import Settings
from lectra_core.db.models import Playlist, ProcessingStage, Video, VideoChunk
from lectra_core.db.session import get_engine, init_db
from lectra_core.vectorstore.qdrant import (
    EXPECTED_VECTOR_SIZE,
    IncompatibleCollectionError,
    QdrantVectorStore,
)
from lectra_core.vectorstore.service import IndexingService
from qdrant_client import models
from sqlalchemy.orm import Session


@pytest.fixture
def mock_db(tmp_path):
    """Temporary SQLite database session for vector store unit tests."""
    db_file = tmp_path / "test_vectorstore.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file}",
        data_dir=tmp_path,
        artifacts_dir=tmp_path / "artifacts",
        temp_audio_dir=tmp_path / "temp_audio",
        model_cache_dir=tmp_path / "models",
    )
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)
    with Session(engine) as session:
        pl = Playlist(
            id="pl_test_id",
            youtube_id="PL_qdrant_test",
            url="https://youtube.com/playlist?list=PL_qdrant_test",
            title="Qdrant Test Playlist",
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.commit()
        yield session, settings


def test_ensure_collection_creates_when_absent():
    """Verify that absent collection is created with size 768 and Cosine distance."""
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = False

    store = QdrantVectorStore(settings=Settings(), client=mock_client)
    store.ensure_collection()

    mock_client.create_collection.assert_called_once()
    args, kwargs = mock_client.create_collection.call_args
    assert kwargs["collection_name"] == "revision_chunks"
    vectors_config = kwargs["vectors_config"]
    assert vectors_config.size == EXPECTED_VECTOR_SIZE
    assert vectors_config.distance == models.Distance.COSINE


def test_ensure_collection_validates_existing_valid_collection():
    """Verify that existing collection matching 768 Cosine passes validation."""
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = True

    mock_info = MagicMock()
    mock_info.config.params.vectors.size = 768
    mock_info.config.params.vectors.distance = models.Distance.COSINE
    mock_info.points_count = 50
    mock_client.get_collection.return_value = mock_info

    store = QdrantVectorStore(settings=Settings(), client=mock_client)
    store.ensure_collection()

    mock_client.create_collection.assert_not_called()


def test_ensure_collection_raises_on_dimension_mismatch():
    """Verify that existing collection with incompatible dimension raises error."""
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = True

    mock_info = MagicMock()
    mock_info.config.params.vectors.size = 384  # Mismatch (e.g. MiniLM instead of Gemma 768)
    mock_info.config.params.vectors.distance = models.Distance.COSINE
    mock_client.get_collection.return_value = mock_info

    store = QdrantVectorStore(settings=Settings(), client=mock_client)
    with pytest.raises(IncompatibleCollectionError, match="vector dimension 384"):
        store.ensure_collection()


def test_ensure_collection_raises_on_metric_mismatch():
    """Verify that existing collection with incompatible metric raises error."""
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = True

    mock_info = MagicMock()
    mock_info.config.params.vectors.size = 768
    mock_info.config.params.vectors.distance = models.Distance.DOT  # Mismatch
    mock_client.get_collection.return_value = mock_info

    store = QdrantVectorStore(settings=Settings(), client=mock_client)
    with pytest.raises(IncompatibleCollectionError, match="distance metric"):
        store.ensure_collection()


def test_payload_construction():
    """Verify payload structure matches specification."""
    service = IndexingService(settings=Settings())

    video = Video(
        id="vid_123",
        playlist_id="pl_123",
        youtube_id="yt_abc",
        title="Test Title",
        url="https://youtube.com/watch?v=yt_abc",
        status="CHUNKED",
    )
    chunk = VideoChunk(
        id="chunk_uuid_1",
        video_id="vid_123",
        chunk_index=2,
        start_seconds=120.5,
        end_seconds=195.5,
        duration_seconds=75.0,
        text="Sample chunk content text",
        token_count=45,
        source_segment_start_index=10,
        source_segment_end_index=25,
    )

    payload = service.construct_payload(video, chunk)
    assert payload["chunk_id"] == "chunk_uuid_1"
    assert payload["video_id"] == "vid_123"
    assert payload["youtube_id"] == "yt_abc"
    assert payload["playlist_id"] == "pl_123"
    assert payload["title"] == "Test Title"
    assert payload["chunk_index"] == 2
    assert payload["start_seconds"] == 120.5
    assert payload["end_seconds"] == 195.5
    assert payload["duration_seconds"] == 75.0
    assert payload["text"] == "Sample chunk content text"
    assert payload["token_count"] == 45
    assert payload["source_segment_start_index"] == 10
    assert payload["source_segment_end_index"] == 25
    assert payload["youtube_url"] == "https://www.youtube.com/watch?v=yt_abc&t=120"


def test_indexing_service_orchestration_and_idempotency(mock_db):
    """Verify full indexing orchestration, point verification, and idempotent update."""
    session, settings = mock_db

    video = Video(
        playlist_id="pl_test_id",
        youtube_id="yt_indexing_test",
        title="Greedy Knapsack",
        url="https://youtube.com/watch?v=yt_indexing_test",
        status="CHUNKED",
    )
    session.add(video)
    session.flush()

    chunk_id = str(uuid.uuid4())
    chunk = VideoChunk(
        id=chunk_id,
        video_id=video.id,
        chunk_index=0,
        start_seconds=0.0,
        end_seconds=75.0,
        duration_seconds=75.0,
        text="Greedy knapsack selects items by ratio.",
        token_count=20,
        source_segment_start_index=0,
        source_segment_end_index=5,
    )
    session.add(chunk)
    session.commit()

    # Mocks for embedding service and vector store
    mock_embed = MagicMock()
    mock_embed.embed_chunks.return_value = [[0.1] * 768]

    mock_store = MagicMock()
    mock_store.retrieve_points.return_value = [MagicMock(id=chunk_id)]

    service = IndexingService(
        settings=settings,
        embedding_service=mock_embed,
        vector_store=mock_store,
    )

    result = service.index_video(session, video)
    assert result.status == "COMPLETED"
    assert result.chunks_indexed == 1
    assert result.verified_points == 1

    session.refresh(video)
    assert video.status == "INDEXED"

    stage = session.query(ProcessingStage).filter_by(
        video_id=video.id, stage_name="INDEXING"
    ).first()
    assert stage is not None
    assert stage.status == "COMPLETED"


def test_indexing_service_failure_recovery_on_verification_mismatch(mock_db):
    """Verify that if points cannot be verified in Qdrant, stage is marked FAILED."""
    session, settings = mock_db

    video = Video(
        playlist_id="pl_test_id",
        youtube_id="yt_failure_test",
        title="Failure Test Video",
        url="https://youtube.com/watch?v=yt_failure_test",
        status="CHUNKED",
    )
    session.add(video)
    session.flush()

    chunk = VideoChunk(
        id=str(uuid.uuid4()),
        video_id=video.id,
        chunk_index=0,
        start_seconds=0.0,
        end_seconds=75.0,
        duration_seconds=75.0,
        text="Some chunk content.",
        token_count=10,
        source_segment_start_index=0,
        source_segment_end_index=2,
    )
    session.add(chunk)
    session.commit()

    mock_embed = MagicMock()
    mock_embed.embed_chunks.return_value = [[0.1] * 768]

    # Store returns 0 points on retrieve, simulating upload drop/failure
    mock_store = MagicMock()
    mock_store.retrieve_points.return_value = []

    service = IndexingService(
        settings=settings,
        embedding_service=mock_embed,
        vector_store=mock_store,
    )

    result = service.index_video(session, video)
    assert result.status == "FAILED"
    assert "Verification failed" in (result.error or "")

    session.refresh(video)
    # Video status should not be advanced to INDEXED
    assert video.status == "CHUNKED"

    stage = session.query(ProcessingStage).filter_by(
        video_id=video.id, stage_name="INDEXING"
    ).first()
    assert stage is not None
    assert stage.status == "FAILED"
    assert stage.error_category == "INDEXING_FAILED"
