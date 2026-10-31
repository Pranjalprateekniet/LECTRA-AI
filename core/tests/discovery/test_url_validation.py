"""Unit tests for playlist URL validation."""

import pytest
from lectra_core.discovery.url_validation import InvalidPlaylistUrlError, validate_playlist_url


def test_validate_standard_playlist_url():
    url = "https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
    result = validate_playlist_url(url)
    assert result.youtube_id == "PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
    assert (
        result.normalized_url
        == "https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
    )


def test_validate_mobile_playlist_url():
    url = "https://m.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ&si=xyz123"
    result = validate_playlist_url(url)
    assert result.youtube_id == "PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
    assert (
        result.normalized_url
        == "https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
    )


def test_validate_watch_url_with_list():
    url = "https://www.youtube.com/watch?v=II6ziNnub1Q&list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
    result = validate_playlist_url(url)
    assert result.youtube_id == "PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
    assert (
        result.normalized_url
        == "https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
    )


def test_validate_empty_url():
    with pytest.raises(InvalidPlaylistUrlError, match="must not be empty"):
        validate_playlist_url("")
    with pytest.raises(InvalidPlaylistUrlError, match="must not be empty"):
        validate_playlist_url("   ")


def test_validate_non_youtube_domain():
    with pytest.raises(InvalidPlaylistUrlError, match="Not a YouTube URL"):
        validate_playlist_url("https://vimeo.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ")


def test_validate_missing_list_param():
    with pytest.raises(InvalidPlaylistUrlError, match="missing the required 'list' parameter"):
        validate_playlist_url("https://www.youtube.com/watch?v=II6ziNnub1Q")


def test_validate_invalid_playlist_id():
    with pytest.raises(InvalidPlaylistUrlError, match="not a valid YouTube playlist ID"):
        validate_playlist_url("https://www.youtube.com/playlist?list=short")
