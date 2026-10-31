"""Shared test helpers for discovery tests (mocked provider + data builders)."""

from typing import List, Optional, Tuple

from lectra_core.discovery.ytdlp_client import (
    PlaylistEntry,
    PlaylistInfo,
    VideoInfo,
    VideoMetadataError,
)


def make_entry(
    index: int, video_id: str, title: str = None, duration: float = 600.0
) -> PlaylistEntry:
    """Build one flat playlist entry."""
    return PlaylistEntry(
        youtube_id=video_id,
        title=title or f"Video {index} title",
        url=f"https://www.youtube.com/watch?v={video_id}",
        duration_seconds=duration,
        position=index,
    )


class FakeProvider:
    """In-memory MetadataProvider double for unit tests.

    - ``playlist_entries``: list of entries returned for get_playlist().
    - ``video_results``: mapping video_url -> VideoInfo (available video).
    - ``video_failures``: mapping video_url -> (category_hint_message) raising VideoMetadataError.
    - ``playlist_error``: exception raised by get_playlist() when set.
    - ``call_log``: list of ("playlist", url) / ("video", url) tuples.
    """

    def __init__(self, entries: List[PlaylistEntry], title: str = "Test playlist"):
        self.playlist_title = title
        self.entries = entries
        self.playlist_error: Optional[Exception] = None
        self.video_results = {}
        for e in entries:
            url = f"https://www.youtube.com/watch?v={e.youtube_id}"
            if url not in self.video_results:
                self.video_results[url] = VideoInfo(
                    youtube_id=e.youtube_id,
                    title=e.title,
                    url=e.url,
                    duration_seconds=e.duration_seconds,
                    availability="public",
                )
        self.video_failures: dict = {}
        self.call_log: List[Tuple[str, str]] = []

    @property
    def playlist_info(self) -> PlaylistInfo:
        return PlaylistInfo(
            youtube_id="PLtest1234567890",
            title=self.playlist_title,
            channel_name="Test channel",
            entries=self.entries,
        )

    def get_playlist(self, url: str) -> PlaylistInfo:
        self.call_log.append(("playlist", url))
        if self.playlist_error is not None:
            raise self.playlist_error
        return self.playlist_info

    def get_video(self, video_url: str) -> VideoInfo:
        self.call_log.append(("video", video_url))
        if video_url in self.video_failures:
            raise VideoMetadataError(video_url, self.video_failures[video_url])
        return self.video_results[video_url]
