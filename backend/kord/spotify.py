from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"

# Phase 1 scopes only. Playback scopes (streaming, user-read-playback-state,
# user-modify-playback-state) arrive with the Web Playback SDK in Phase 2.
SCOPES = "user-top-read user-read-recently-played user-library-read"

# Spotify's February 2026 development-mode change cut the search `limit` maximum
# from 50 to 10 (existing apps migrated 2026-03-09). Exceeding it returns a 400
# reading "Invalid limit", which points at the parameter rather than the quota
# mode and is easy to chase in the wrong direction.
SEARCH_LIMIT_MAX = 10


class SpotifyError(Exception):
    """A failed Spotify call, carrying the reason Spotify actually gave.

    `raise_for_status()` discards the response body, which is exactly where
    Spotify explains what was wrong — leaving only an opaque 500 downstream.
    """

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(f"Spotify returned {status}: {message}")


def _raise_for_spotify(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        body = response.json()
        message = body.get("error", {})
        message = message.get("message") if isinstance(message, dict) else str(message)
        message = message or body.get("error_description") or str(body)
    except Exception:
        message = response.text[:300] or response.reason_phrase
    raise SpotifyError(response.status_code, message)


def build_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def authorize_url(client_id: str, redirect_uri: str, challenge: str, scopes: str) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "scope": scopes,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


class SpotifyClient:
    """Spotify Web API, restricted to endpoints that still exist.

    audio-features, audio-analysis, recommendations, related-artists and
    preview_url were all deprecated for new apps on 2024-11-27 (spec section
    2.1). Nothing here touches them.
    """

    def __init__(self, client_id: str, http: httpx.AsyncClient | None = None) -> None:
        self.client_id = client_id
        self._http = http

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=15.0)
        return self._http

    async def exchange_code(self, code: str, verifier: str, redirect_uri: str) -> dict:
        http = await self._client()
        response = await http.post(TOKEN_URL, data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": redirect_uri, "client_id": self.client_id,
            "code_verifier": verifier,
        })
        _raise_for_spotify(response)
        return response.json()

    async def refresh(self, refresh_token: str) -> dict:
        http = await self._client()
        response = await http.post(TOKEN_URL, data={
            "grant_type": "refresh_token", "refresh_token": refresh_token,
            "client_id": self.client_id,
        })
        _raise_for_spotify(response)
        return response.json()

    async def search_tracks(
        self, query: str, access_token: str, limit: int = SEARCH_LIMIT_MAX
    ) -> list[dict]:
        http = await self._client()
        response = await http.get(
            f"{API_BASE}/search",
            params={
                "q": query, "type": "track",
                "limit": max(1, min(limit, SEARCH_LIMIT_MAX)),
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _raise_for_spotify(response)
        return [self._track(item) for item in response.json()["tracks"]["items"]]

    async def get_track(self, track_id: str, access_token: str) -> dict:
        http = await self._client()
        response = await http.get(
            f"{API_BASE}/tracks/{track_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _raise_for_spotify(response)
        return self._track(response.json())

    @staticmethod
    def _track(item: dict) -> dict:
        images = item.get("album", {}).get("images") or []
        return {
            "id": item["id"],
            "title": item["name"],
            "artist": ", ".join(a["name"] for a in item.get("artists", [])),
            "album": item.get("album", {}).get("name"),
            "duration_ms": item["duration_ms"],
            "image": images[0]["url"] if images else None,
        }
