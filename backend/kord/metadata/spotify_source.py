"""Song facts from Spotify, for a signed-in user.

Thin: the HTTP client already exists. This adapts its dict-returning methods to
TrackFacts so the rest of the app never learns which catalogue answered.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from kord.metadata.source import TrackFacts


def facts_from_spotify(track: dict) -> TrackFacts:
    return TrackFacts(
        id=track["id"],          # bare, per the ID convention
        title=track["title"],
        artist=track["artist"],
        album=track.get("album"),
        duration_ms=int(track["duration_ms"]),
        image=track.get("image"),
    )


class SpotifyMetadata:
    def __init__(self, client, token: Callable[[], Awaitable[str]]) -> None:
        self._client = client
        self._token = token

    async def search(self, query: str, limit: int = 20) -> list[TrackFacts]:
        tracks = await self._client.search_tracks(query, await self._token())
        return [facts_from_spotify(t) for t in tracks]

    async def get(self, track_id: str) -> TrackFacts:
        return facts_from_spotify(
            await self._client.get_track(track_id, await self._token()))
