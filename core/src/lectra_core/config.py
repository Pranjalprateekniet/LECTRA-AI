"""Centralized application configuration and validation."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application Environment
    environment: Literal["development", "production", "testing"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    # Server Settings
    backend_host: str = "127.0.0.1"
    backend_port: int = Field(default=8000, ge=1, le=65535)
    frontend_port: int = Field(default=3000, ge=1, le=65535)

    # Persistent Storage Paths
    data_dir: Path = Path("./data")
    sqlite_path: Path = Path("./data/revision_rag.db")
    artifacts_dir: Path = Path("./data/artifacts")
    temp_audio_dir: Path = Path("./data/temp_audio")
    model_cache_dir: Path = Path("./data/models")

    # Database
    database_url: str = "sqlite:///./data/revision_rag.db"

    # Vector Store (Qdrant)
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "revision_chunks"
    qdrant_api_key: Optional[str] = None

    @field_validator("qdrant_url", mode="before")
    @classmethod
    def validate_qdrant_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("QDRANT_URL must not be empty")
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("QDRANT_URL must start with http:// or https://")
        return v

    @field_validator("qdrant_api_key", mode="before")
    @classmethod
    def validate_qdrant_api_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if v == "":
            return None
        return v

    # Embeddings — Phase 5
    embedding_model_name: str = "google/embeddinggemma-2"
    embedding_device: Literal["cpu", "cuda", "auto"] = "cuda"
    embedding_batch_size: int = Field(default=8, ge=1)
    embedding_dimensions: int = 768

    # Speech Recognition (faster-whisper) — Phase 3.2
    # Model name: tiny.en, base.en, small.en, medium.en, large-v3, etc.
    whisper_model_name: str = "small.en"
    # Device: "cpu", "cuda", or "auto" (auto detects CUDA and falls back to CPU)
    whisper_device: Literal["cpu", "cuda", "auto"] = "auto"
    # Compute type: "auto" (resolves to float16 on cuda, int8 on cpu), or explicit
    # ("int8", "float16", "float32", etc.)
    whisper_compute_type: str = "auto"
    # Beam size for decoding. Larger values improve accuracy at the cost of speed.
    whisper_beam_size: int = Field(default=5, ge=1)
    # Maximum seconds to spend downloading audio for a single video.
    whisper_audio_download_timeout_seconds: int = Field(default=300, ge=10)

    @field_validator("whisper_compute_type", mode="before")
    @classmethod
    def validate_whisper_compute_type(cls, v: Any) -> str:
        allowed = {
            "auto",
            "int8",
            "int8_float16",
            "int8_bfloat16",
            "float16",
            "bfloat16",
            "float32",
        }
        v = str(v).strip().lower()
        if v not in allowed:
            raise ValueError(f"whisper_compute_type must be one of {allowed}, got {v!r}")
        return v

    # Translation (Argos Translate)
    translation_source_lang: str = "hi"
    translation_target_lang: str = "en"

    # LLM Provider
    llm_provider: Literal["groq", "gpt-oss"] = "groq"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    groq_api_key: Optional[str] = None

    # Worker Settings
    worker_concurrency: int = Field(default=1, ge=1)
    worker_max_retries: int = Field(default=3, ge=0)
    worker_poll_interval_seconds: float = Field(default=2.0, ge=0.1)
    worker_retry_delay_seconds: float = Field(default=5.0, ge=0.0)

    # Playlist discovery (Stage A)
    discovery_socket_timeout_seconds: int = Field(default=30, ge=1)

    # Subtitle / Transcript Acquisition (Phase 3.1)
    # Only English subtitles are extracted.  Videos without English captions
    # are marked NEEDS_TRANSCRIPTION for a future Whisper fallback stage.
    subtitle_languages: list[str] = Field(default_factory=lambda: ["en"])
    subtitle_prefer_manual: bool = True
    subtitle_socket_timeout_seconds: int = Field(default=30, ge=1)

    @field_validator("subtitle_languages", mode="before")
    @classmethod
    def validate_subtitle_languages(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            langs = [item.strip() for item in v.split(",") if item.strip()]
            return langs or ["en"]
        if isinstance(v, (list, tuple)):
            return [str(item).strip() for item in v if str(item).strip()]
        return ["en"]

    # Hardware Acceleration
    execution_device: Literal["cpu", "cuda"] = "cpu"

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_db_url(cls, v: Optional[str], info) -> str:
        if v:
            return v
        data = info.data
        sqlite_path = data.get("sqlite_path", Path("./data/revision_rag.db"))
        return f"sqlite:///{sqlite_path}"

    def ensure_directories(self) -> None:
        """Create configured persistent storage directories if they do not exist."""
        for path in [
            self.data_dir,
            self.sqlite_path.parent,
            self.artifacts_dir,
            self.temp_audio_dir,
            self.model_cache_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retrieve cached application settings instance."""
    return Settings()
