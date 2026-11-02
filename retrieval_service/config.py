"""Configuration for the hosted read-only retrieval service."""

from functools import lru_cache
from typing import Any, List, Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RetrievalServiceSettings(BaseSettings):
    """Centralized configuration for the hosted retrieval API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Server settings
    host: str = "0.0.0.0"
    port: int = Field(default=8001, ge=1, le=65535)
    environment: Literal["development", "production", "testing"] = "production"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    # Qdrant Cloud settings (Read-only access)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    qdrant_collection_name: str = "revision_chunks"
    qdrant_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)

    @field_validator("qdrant_url", mode="before")
    @classmethod
    def validate_qdrant_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("QDRANT_URL must not be empty.")
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("QDRANT_URL must start with http:// or https://")
        return v

    @field_validator("qdrant_api_key", mode="before")
    @classmethod
    def validate_qdrant_api_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = str(v).strip()
        return v if v else None

    @field_validator("qdrant_collection_name", mode="before")
    @classmethod
    def validate_collection_name(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("QDRANT_COLLECTION_NAME must not be empty.")
        return str(v).strip()

    # Embedding model configuration (exact ingestion model)
    embedding_model_name: str = "google/embeddinggemma-2"
    embedding_device: Literal["cpu", "cuda", "auto"] = "auto"

    # Rate limiting & abuse protection
    redis_url: Optional[str] = None
    rate_limit_per_minute: int = Field(default=10, ge=1)
    rate_limit_per_hour: int = Field(default=100, ge=1)
    max_query_length: int = Field(default=1000, ge=10, le=5000)
    max_top_k: int = Field(default=10, ge=1, le=50)
    default_top_k: int = Field(default=5, ge=1, le=10)

    # Concurrency and timeout controls
    max_concurrent_requests: int = Field(default=10, ge=1, le=100)
    request_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)

    # Network, CORS & Trusted Proxies
    trusted_proxies: List[str] = Field(default_factory=lambda: ["127.0.0.1", "::1"])
    # CORS is disabled by default because retrieval is a server-to-server workflow.
    # Set CORS_ORIGINS explicitly if browser clients need direct access.
    cors_origins: List[str] = Field(default_factory=list)

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def parse_trusted_proxies(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            items = [item.strip() for item in v.split(",") if item.strip()]
            return items if items else ["127.0.0.1", "::1"]
        if isinstance(v, (list, tuple)):
            return [str(item).strip() for item in v if str(item).strip()]
        return ["127.0.0.1", "::1"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, (list, tuple)):
            return [str(item).strip() for item in v if str(item).strip()]
        return []

    @field_validator("redis_url", mode="before")
    @classmethod
    def clean_redis_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = str(v).strip()
        return v if v else None


@lru_cache(maxsize=1)
def get_service_settings() -> RetrievalServiceSettings:
    """Retrieve cached retrieval service configuration."""
    return RetrievalServiceSettings()

