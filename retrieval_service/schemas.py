"""Request and response schemas for the hosted retrieval API."""

from typing import Any, List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RetrieveRequest(BaseModel):
    """Client request schema for semantic retrieval."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language question or search query (maximum 1000 characters)",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of top relevant chunks to retrieve (maximum 10)",
    )

    @field_validator("query", mode="before")
    @classmethod
    def validate_query(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("Query must be a string.")
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Query cannot be empty or whitespace only.")
        if len(cleaned) > 1000:
            raise ValueError("Query exceeds maximum allowed length of 1000 characters.")
        return cleaned


class RetrieveResultItem(BaseModel):
    """A single retrieved transcript chunk with timestamp citation and metadata."""

    model_config = ConfigDict(extra="ignore")

    video_title: str
    text: str
    start_timestamp: float
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    youtube_url: str
    score: float
    similarity_score: float
    chunk_id: str
    video_id: str
    youtube_id: str
    playlist_id: str
    chunk_index: int


class RetrieveResponse(BaseModel):
    """API response envelope for semantic retrieval."""

    model_config = ConfigDict(extra="ignore")

    success: bool = True
    results: List[RetrieveResultItem]


class HealthCheckResponse(BaseModel):
    """Operational health status response."""

    model_config = ConfigDict(extra="ignore")

    status: str
    qdrant_status: str
    embedding_model: str
    version: str

