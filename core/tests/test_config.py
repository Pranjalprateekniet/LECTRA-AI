"""Unit tests for configuration validation."""

import pytest
from lectra_core.config import Settings
from pydantic import ValidationError


def test_default_settings():
    """Verify default configuration values."""
    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.backend_port == 8000
    assert settings.frontend_port == 3000
    assert settings.database_url.startswith("sqlite:///")
    assert settings.execution_device == "cpu"
    assert settings.llm_provider in ("groq", "gpt-oss")
    # Qdrant defaults
    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.qdrant_collection_name == "revision_chunks"
    assert settings.qdrant_api_key is None


def test_invalid_port_validation():
    """Verify that invalid port numbers raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(backend_port=70000)
    assert "backend_port" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(backend_port=0)
    assert "backend_port" in str(exc_info.value)


def test_invalid_device_validation():
    """Verify that unsupported devices raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(execution_device="tpu")
    assert "execution_device" in str(exc_info.value)


def test_invalid_qdrant_url_validation():
    """Verify that invalid Qdrant URLs raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(qdrant_url="")
    assert "QDRANT_URL must not be empty" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(qdrant_url="ftp://invalid.com")
    assert "must start with http:// or https://" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(qdrant_url="just-a-host")
    assert "must start with http:// or https://" in str(exc_info.value)


def test_valid_qdrant_url_cloud():
    """Verify Qdrant Cloud URL is accepted."""
    settings = Settings(qdrant_url="https://cluster-xxxxxxxxxx.region.aws.cloud.qdrant.io")
    assert settings.qdrant_url == "https://cluster-xxxxxxxxxx.region.aws.cloud.qdrant.io"


def test_valid_qdrant_url_local():
    """Verify local Qdrant URL is accepted."""
    settings = Settings(qdrant_url="http://localhost:6333")
    assert settings.qdrant_url == "http://localhost:6333"

    settings = Settings(qdrant_url="http://127.0.0.1:6333")
    assert settings.qdrant_url == "http://127.0.0.1:6333"


def test_qdrant_api_key_none_when_empty():
    """Verify empty QDRANT_API_KEY becomes None."""
    settings = Settings(qdrant_api_key="")
    assert settings.qdrant_api_key is None

    settings = Settings(qdrant_api_key="   ")
    assert settings.qdrant_api_key is None


def test_qdrant_api_key_preserved():
    """Verify valid QDRANT_API_KEY is preserved."""
    settings = Settings(qdrant_api_key="test-api-key-123")
    assert settings.qdrant_api_key == "test-api-key-123"


def test_directory_creation(tmp_path):
    """Verify directory creation helper creates expected folders."""
    data_dir = tmp_path / "data"
    settings = Settings(
        data_dir=data_dir,
        sqlite_path=data_dir / "test.db",
        artifacts_dir=data_dir / "artifacts",
        temp_audio_dir=data_dir / "temp_audio",
        model_cache_dir=data_dir / "models",
    )
    settings.ensure_directories()
    assert data_dir.exists()
    assert (data_dir / "artifacts").exists()
    assert (data_dir / "temp_audio").exists()
    assert (data_dir / "models").exists()
