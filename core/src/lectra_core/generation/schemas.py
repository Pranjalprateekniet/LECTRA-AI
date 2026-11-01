"""Pydantic data schemas for grounded answer generation and citations."""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

AnswerStatus = Literal["answered", "partially_answered", "insufficient_context"]


class CitationItem(BaseModel):
    """Citation linking an answer segment to a verified timestamped YouTube segment."""

    model_config = ConfigDict(extra="ignore")

    source_id: str = Field(..., description="Assigned reference token, e.g. S1")
    video_title: str = Field(..., description="Title of the source video")
    youtube_id: str = Field(..., description="11-character YouTube video ID")
    chunk_index: int = Field(..., ge=0, description="0-indexed chunk position in video")
    start_seconds: float = Field(..., ge=0.0, description="Start time in seconds")
    end_seconds: float = Field(..., ge=0.0, description="End time in seconds")
    youtube_url: str = Field(..., description="Constructed timestamped video link")
    text: Optional[str] = Field(default=None, description="Original transcript chunk text excerpt")
    chunk_id: Optional[str] = Field(default=None, description="Unique chunk UUID")
    playlist_id: Optional[str] = Field(default=None, description="Playlist UUID")


class LLMRawAnswer(BaseModel):
    """Schema expected directly from the LLM JSON response."""

    model_config = ConfigDict(extra="ignore")

    status: AnswerStatus = Field(
        ...,
        description="Whether the query was answered, partially answered, or insufficient context",
    )
    answer: str = Field(..., description="Generated explanation grounded in lecture transcript")
    citations: List[str] = Field(
        default_factory=list,
        description="List of cited source IDs (e.g. ['S1', 'S3'])",
    )

    @field_validator("citations", mode="before")
    @classmethod
    def clean_citation_list(cls, v: object) -> List[str]:
        if not v:
            return []
        if isinstance(v, list):
            cleaned = []
            for item in v:
                s = str(item).strip().strip("[]")
                if s:
                    cleaned.append(s)
            return cleaned
        if isinstance(v, str):
            s = v.strip().strip("[]")
            return [s] if s else []
        return []


class GenerationRequest(BaseModel):
    """Request schema for RAG answer generation."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="Student revision question")
    top_k: Optional[int] = Field(
        default=None, ge=1, le=100, description="Number of chunks to retrieve"
    )
    score_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional minimum similarity score threshold",
    )
    playlist_id: Optional[str] = Field(default=None, description="Optional playlist UUID filter")
    video_id: Optional[str] = Field(default=None, description="Optional video UUID filter")
    youtube_id: Optional[str] = Field(default=None, description="Optional YouTube video ID filter")

    @field_validator("query", mode="before")
    @classmethod
    def validate_query(cls, v: object) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Query string must not be empty or whitespace only.")
        return v.strip()

    @field_validator("playlist_id", "video_id", "youtube_id", mode="before")
    @classmethod
    def clean_filter_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = str(v).strip()
        return v if v else None


class AnswerResponse(BaseModel):
    """Final API response containing structured answer and verified citations."""

    model_config = ConfigDict(extra="ignore")

    status: AnswerStatus
    answer: str
    citations: List[CitationItem]
