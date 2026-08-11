import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import httpx

from kord.spotify import SCOPES, SpotifyClient, authorize_url, build_pkce_pair


def test_pkce_challenge_is_the_s256_of_the_verifier():
    verifier, challenge = build_pkce_pair()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert challenge == expected
    assert 43 <= len(verifier) <= 128


def test_pkce_pairs_are_unique_per_call():
    assert build_pkce_pair()[0] != build_pkce_pair()[0]


def test_authorize_url_carries_required_params():
    _, challenge = build_pkce_pair()
    url = authorize_url("cid", "http://localhost:8000/cb", challenge, SCOPES)
    params = parse_qs(urlparse(url).query)
    assert params["client_id"] == ["cid"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["response_type"] == ["code"]
    assert "user-top-read" in params["scope"][0]


def test_phase_1_scopes_exclude_playback():
    """Playback scopes belong to Phase 2 - do not request what we cannot use yet."""
    assert "streaming" not in SCOPES
    assert "user-modify-playback-state" not in SCOPES


async def test_search_tracks_parses_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"tracks": {"items": [{
            "id": "abc", "name": "Creep", "duration_ms": 238640,
            "artists": [{"name": "Radiohead"}],
            "album": {"name": "Pablo Honey",
                      "images": [{"url": "https://img.invalid/1.jpg"}]},
        }]}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        results = await SpotifyClient("cid", http=http).search_tracks("creep", "tok")
    assert results[0]["artist"] == "Radiohead"
    assert results[0]["title"] == "Creep"
    assert results[0]["duration_ms"] == 238640
    assert results[0]["image"] == "https://img.invalid/1.jpg"


async def test_missing_album_art_does_not_crash():
    def handler(request):
        return httpx.Response(200, json={"tracks": {"items": [{
            "id": "abc", "name": "X", "duration_ms": 1000,
            "artists": [{"name": "Y"}], "album": {"name": "Z", "images": []},
        }]}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        results = await SpotifyClient("cid", http=http).search_tracks("x", "tok")
    assert results[0]["image"] is None


async def test_multiple_artists_are_joined():
    def handler(request):
        return httpx.Response(200, json={"tracks": {"items": [{
            "id": "abc", "name": "Song", "duration_ms": 1000,
            "artists": [{"name": "A"}, {"name": "B"}],
            "album": {"name": "Z", "images": []},
        }]}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        results = await SpotifyClient("cid", http=http).search_tracks("x", "tok")
    assert results[0]["artist"] == "A, B"


async def test_get_track_returns_the_same_shape_as_search():
    def handler(request):
        return httpx.Response(200, json={
            "id": "abc", "name": "Creep", "duration_ms": 238640,
            "artists": [{"name": "Radiohead"}],
            "album": {"name": "Pablo Honey", "images": []},
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        track = await SpotifyClient("cid", http=http).get_track("abc", "tok")
    assert set(track) == {"id", "title", "artist", "album", "duration_ms", "image"}


async def test_exchange_code_sends_the_verifier():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": "at", "refresh_token": "rt"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        tokens = await SpotifyClient("cid", http=http).exchange_code(
            "code123", "verifier456", "http://localhost:8000/cb")
    assert tokens["access_token"] == "at"
    assert "code_verifier=verifier456" in seen["body"]
    assert "grant_type=authorization_code" in seen["body"]
