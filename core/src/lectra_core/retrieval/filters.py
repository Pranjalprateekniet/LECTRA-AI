"""Filter builders and validators for Qdrant vector retrieval."""

from typing import Any, List, Optional

from qdrant_client import models

from lectra_core.retrieval.schemas import RetrievalFilter


def build_qdrant_filter(
    filters: Optional[RetrievalFilter] = None,
    playlist_id: Optional[str] = None,
    video_id: Optional[str] = None,
    youtube_id: Optional[str] = None,
) -> Optional[models.Filter]:
    """Construct a Qdrant Filter from optional metadata constraints.

    Can accept either a RetrievalFilter instance or individual keyword arguments.
    Combines all supplied constraints with Boolean AND ('must').
    """
    p_id = filters.playlist_id if filters else playlist_id
    v_id = filters.video_id if filters else video_id
    y_id = filters.youtube_id if filters else youtube_id

    conditions: List[Any] = []

    if p_id and p_id.strip():
        conditions.append(
            models.FieldCondition(
                key="playlist_id",
                match=models.MatchValue(value=p_id.strip()),
            )
        )

    if v_id and v_id.strip():
        conditions.append(
            models.FieldCondition(
                key="video_id",
                match=models.MatchValue(value=v_id.strip()),
            )
        )

    if y_id and y_id.strip():
        conditions.append(
            models.FieldCondition(
                key="youtube_id",
                match=models.MatchValue(value=y_id.strip()),
            )
        )

    if not conditions:
        return None

    return models.Filter(must=conditions)
