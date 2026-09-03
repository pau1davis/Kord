import json
from pathlib import Path

import pytest

from kord.metadata.itunes import ItunesMetadata, facts_from_itunes

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "itunes_search.json").read_text())


def test_itunes_results_become_track_facts():
    facts = facts_from_itunes(FIXTURE)
    assert facts, "fixture should contain results"
    first = facts[0]
    assert first.artist == "Pantera"
    assert "Mouth for War" in first.title
    assert first.id.startswith("itunes:")


def test_duration_is_milliseconds_not_seconds():
    """The one mapping that must not be wrong. Duration is what picks the right
    upload and rejects live takes, so a value in the wrong unit would not crash
    — it would quietly start choosing wrong recordings."""
    facts = facts_from_itunes(FIXTURE)
    assert all(100_000 < f.duration_ms < 900_000 for f in facts), \
        [f.duration_ms for f in facts]


def test_a_result_with_no_duration_is_dropped_not_zeroed():
    # A zero duration would be classified 'reject' anyway, but silently: it
    # would look like a candidate that failed validation rather than metadata
    # that never arrived.
    facts = facts_from_itunes({"results": [
        {"trackId": 1, "trackName": "x", "artistName": "y"}]})
    assert facts == []


def test_missing_artwork_is_none_not_a_broken_url():
    facts = facts_from_itunes({"results": [{
        "trackId": 1, "trackName": "x", "artistName": "y",
        "trackTimeMillis": 200000}]})
    assert facts[0].image is None


def test_artwork_is_upgraded_past_the_thumbnail_size():
    """iTunes returns a 100px thumbnail; the home screen orbits these at up to
    340px and a 100px source is visibly soft."""
    facts = facts_from_itunes({"results": [{
        "trackId": 1, "trackName": "x", "artistName": "y",
        "trackTimeMillis": 200000,
        "artworkUrl100": "https://example.test/a/100x100bb.jpg"}]})
    assert "600x600" in facts[0].image


def test_an_empty_response_is_not_a_crash():
    assert facts_from_itunes({"resultCount": 0, "results": []}) == []


@pytest.mark.asyncio
async def test_search_asks_itunes_and_returns_facts():
    """No network: a stub client stands in for httpx."""
    class StubResponse:
        status_code = 200
        def json(self): return FIXTURE
        def raise_for_status(self): pass

    class StubClient:
        def __init__(self): self.params = None
        async def get(self, url, params=None):
            self.params = params
            return StubResponse()

    client = StubClient()
    facts = await ItunesMetadata(client=client).search("mouth for war")
    assert facts[0].artist == "Pantera"
    assert client.params["entity"] == "song"
    assert client.params["term"] == "mouth for war"
