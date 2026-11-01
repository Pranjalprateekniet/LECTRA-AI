"""Unit tests for Qdrant retrieval filter construction and validation."""

from lectra_core.retrieval.filters import build_qdrant_filter
from lectra_core.retrieval.schemas import RetrievalFilter
from qdrant_client import models


def test_build_filter_empty_returns_none():
    """Verify that empty inputs produce None (no Qdrant filter)."""
    assert build_qdrant_filter() is None
    assert build_qdrant_filter(filters=RetrievalFilter()) is None
    assert build_qdrant_filter(playlist_id="", video_id="   ", youtube_id=None) is None


def test_build_filter_single_field():
    """Verify individual field conditions use exact keyword MatchValue."""
    f_pl = build_qdrant_filter(playlist_id="pl_123")
    assert f_pl is not None
    assert len(f_pl.must) == 1
    cond = f_pl.must[0]
    assert isinstance(cond, models.FieldCondition)
    assert cond.key == "playlist_id"
    assert cond.match == models.MatchValue(value="pl_123")

    f_vid = build_qdrant_filter(video_id="vid_456")
    assert f_vid is not None
    assert len(f_vid.must) == 1
    assert f_vid.must[0].key == "video_id"
    assert f_vid.must[0].match == models.MatchValue(value="vid_456")

    f_yt = build_qdrant_filter(youtube_id="II6ziNnub1Q")
    assert f_yt is not None
    assert len(f_yt.must) == 1
    assert f_yt.must[0].key == "youtube_id"
    assert f_yt.must[0].match == models.MatchValue(value="II6ziNnub1Q")


def test_build_filter_combined_fields():
    """Verify combined filters generate an AND ('must') filter containing all conditions."""
    filters = RetrievalFilter(
        playlist_id="pl_abc",
        video_id="vid_def",
        youtube_id="yt_ghi",
    )
    q_filter = build_qdrant_filter(filters)
    assert q_filter is not None
    assert len(q_filter.must) == 3

    keys = {cond.key: cond.match.value for cond in q_filter.must}
    assert keys == {
        "playlist_id": "pl_abc",
        "video_id": "vid_def",
        "youtube_id": "yt_ghi",
    }


def test_retrieval_filter_schema_whitespace_stripping():
    """Verify that Pydantic filter schema strips whitespace and normalizes blanks to None."""
    rf = RetrievalFilter(playlist_id="  pl_1  ", video_id="   ", youtube_id=None)
    assert rf.playlist_id == "pl_1"
    assert rf.video_id is None
    assert rf.youtube_id is None

