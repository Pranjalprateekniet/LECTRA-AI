"""Playlist repository: reconciliation helpers keyed by stable YouTube ID."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from lectra_core.db.models import Playlist


def get_by_youtube_id(session: Session, youtube_id: str) -> Optional[Playlist]:
    """Fetch a playlist by its stable YouTube playlist ID, if present."""
    return session.scalars(select(Playlist).where(Playlist.youtube_id == youtube_id)).first()


def upsert_from_record(
    session: Session,
    youtube_id: str,
    normalized_url: str,
    defaults: dict,
) -> Playlist:
    """Insert the playlist the first time it is seen; update metadata on rediscovery.

    ``defaults`` holds fields to apply on insert (and non-identity updates).
    ``status`` and ``discovery_error`` are caller-controlled so the service can
    mark progress without clobbering a completed manifest on resubmission.
    """
    playlist = session.scalars(select(Playlist).where(Playlist.youtube_id == youtube_id)).first()
    if playlist is None:
        playlist = Playlist(youtube_id=youtube_id, url=normalized_url, **defaults)
        session.add(playlist)
    else:
        playlist.url = normalized_url
        for field, value in defaults.items():
            setattr(playlist, field, value)
    return playlist
