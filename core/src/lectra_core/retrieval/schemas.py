"""Pydantic data schemas for semantic retrieval."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RetrievalFilter(BaseModel):
    """Optional metadata filters for Qdrant vector search."""

    model_config = ConfigDict(extra="forbid")

    playlist_id: Optional[str] = Field(default=None, description="Filter by playlist UUID")
    video_id: Optional[str] = Field(default=None, description="Filter by internal video UUID")
    youtube_id: Optional[str] = Field(default=None, description="Filter by YouTube video ID")

    @field_validator("playlist_id", "video_id", "youtube_id", mode="before")
    @classmethod
    def clean_string_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = str(v).strip()
        return v if v else None


class RetrievalQuery(BaseModel):
    """Request schema for semantic similarity search."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="Natural language revision question")
    top_k: Optional[int] = Field(
        default=None, ge=1, le=100, description="Number of chunks to return"
    )
    score_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional minimum cosine similarity threshold (disabled by default)",
    )
    playlist_id: Optional[str] = Field(default=None, description="Optional playlist UUID filter")
    video_id: Optional[str] = Field(default=None, description="Optional video UUID filter")
    youtube_id: Optional[str] = Field(default=None, description="Optional YouTube ID filter")

    @field_validator("query", mode="before")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Query string must not be empty or whitespace only.")
        return v.strip()

    @field_validator("playlist_id", "video_id", "youtube_id", mode="before")
    @classmethod
    def clean_filter_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = str(v).strip()
        return v if v else None

    @property
    def filters(self) -> RetrievalFilter:
        """Extract populated filter conditions."""
        return RetrievalFilter(
            playlist_id=self.playlist_id,
            video_id=self.video_id,
            youtube_id=self.youtube_id,
        )


class SearchResultItem(BaseModel):
    """Retrieved transcript chunk with source metadata and timestamped citation."""

    model_config = ConfigDict(extra="ignore")

    chunk_id: str
    video_id: str
    youtube_id: str
    playlist_id: str
    video_title: str
    chunk_index: int
    text: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    similarity_score: float
    youtube_url: str


class SearchResponse(BaseModel):
    """API response envelope for semantic search."""

    model_config = ConfigDict(extra="ignore")

    query: str
    results: List[SearchResultItem]
    total_results: int
