"""Playlist URL parsing and validation.

A playlist URL is valid only when it identifies a YouTube playlist ID.
The canonical normalized URL is ``https://www.youtube.com/playlist?list=<ID>``.
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{12,64}$")

_YOUTUBE_HOSTS = {
    "www.youtube.com",
    "youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}

_PLAYLIST_URL_PATHS = {"playlist", "playlists", "watch", ""}


@dataclass(frozen=True)
class PlaylistUrl:
    """A validated playlist URL and its stable YouTube playlist ID."""

    youtube_id: str
    normalized_url: str


class InvalidPlaylistUrlError(ValueError):
    """Raised when a supplied URL does not identify a playable YouTube playlist."""


def validate_playlist_url(url: str) -> PlaylistUrl:
    """Validate a user-supplied playlist URL and return its normalized form.

    Accepts forms such as:
      - https://www.youtube.com/playlist?list=<ID>
      - https://m.youtube.com/playlist?list=<ID>&si=...
      - https://www.youtube.com/watch?v=<VIDEO>&list=<ID>

    Raises InvalidPlaylistUrlError for anything that does not identify a playlist.
    """
    if not url or not url.strip():
        raise InvalidPlaylistUrlError("Playlist URL must not be empty.")
    url = url.strip()

    try:
        parsed = urlparse(url)
    except ValueError as exc:  # e.g. malformed IPv6 in URL
        raise InvalidPlaylistUrlError(f"Could not parse playlist URL: {exc}") from exc

    if parsed.scheme not in ("http", "https"):
        raise InvalidPlaylistUrlError("Playlist URL must start with http:// or https://.")
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        raise InvalidPlaylistUrlError(f"Not a YouTube URL (host '{host or 'unknown'}').")
    if parsed.path.strip("/").split("?")[0].strip("/") not in _PLAYLIST_URL_PATHS:
        raise InvalidPlaylistUrlError(
            f"URL path '{parsed.path}' does not point to a YouTube playlist."
        )

    query = parse_qs(parsed.query)
    list_ids = query.get("list", [])
    if not list_ids or not list_ids[0].strip():
        raise InvalidPlaylistUrlError("Playlist URL is missing the required 'list' parameter.")

    playlist_id = list_ids[0].strip()
    if not _PLAYLIST_ID_RE.match(playlist_id):
        raise InvalidPlaylistUrlError(f"'{playlist_id}' is not a valid YouTube playlist ID.")

    return PlaylistUrl(
        youtube_id=playlist_id,
        normalized_url=f"https://www.youtube.com/playlist?list={playlist_id}",
    )
