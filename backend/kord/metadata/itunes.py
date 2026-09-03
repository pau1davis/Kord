"""Song facts from Apple's iTunes Search API.

No account, no key, no OAuth — which is the whole reason Kord can now be used
without signing in to anything. It returns exactly what Kord needs, and
`trackTimeMillis` is the field that matters most: duration is how the audio
pipeline picks the right upload and rejects live takes.
"""
from __future__ import annotations

import httpx

from kord.metadata.ids import ITUNES, namespaced, native_id_of
from kord.metadata.source import TrackFacts

SEARCH_URL = "https://itunes.apple.com/search"
LOOKUP_URL = "https://itunes.apple.com/lookup"


def _artwork(result: dict) -> str | None:
    url = result.get("artworkUrl100")
    if not url:
        return None
    # The API only offers a 100px thumbnail in search results, but the same
    # path serves any size. The home screen orbits art at up to 340px.
    return url.replace("100x100bb", "600x600bb")


def facts_from_itunes(payload: dict) -> list[TrackFacts]:
    """Map an iTunes response. Results without a duration are dropped.

    A zero duration would be classified 'reject' downstream anyway, but
    silently — it would look like a candidate that failed validation rather
    than metadata that never arrived.
    """
    facts = []
    for result in payload.get("results", []):
        duration = result.get("trackTimeMillis")
        if not duration:
            continue
        facts.append(TrackFacts(
            id=namespaced(ITUNES, str(result["trackId"])),
            title=result.get("trackName", ""),
            artist=result.get("artistName", ""),
            album=result.get("collectionName"),
            duration_ms=int(duration),
            image=_artwork(result),
        ))
    return facts


class ItunesMetadata:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _http(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def search(self, query: str, limit: int = 20) -> list[TrackFacts]:
        http = await self._http()
        response = await http.get(SEARCH_URL, params={
            "term": query, "entity": "song", "limit": max(1, min(limit, 50)),
        })
        response.raise_for_status()
        return facts_from_itunes(response.json())

    async def get(self, track_id: str) -> TrackFacts:
        http = await self._http()
        response = await http.get(
            LOOKUP_URL, params={"id": native_id_of(track_id)})
        response.raise_for_status()
        facts = facts_from_itunes(response.json())
        if not facts:
            raise LookupError(f"iTunes has no track {track_id}")
        return facts[0]
