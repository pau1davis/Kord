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
        response.raise_for_status()
        return response.json()

    async def refresh(self, refresh_token: str) -> dict:
        http = await self._client()
        response = await http.post(TOKEN_URL, data={
            "grant_type": "refresh_token", "refresh_token": refresh_token,
            "client_id": self.client_id,
        })
        response.raise_for_status()
        return response.json()

    async def search_tracks(self, query: str, access_token: str, limit: int = 20) -> list[dict]:
        http = await self._client()
        response = await http.get(
            f"{API_BASE}/search",
            params={"q": query, "type": "track", "limit": limit},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return [self._track(item) for item in response.json()["tracks"]["items"]]

    async def get_track(self, track_id: str, access_token: str) -> dict:
        http = await self._client()
        response = await http.get(
            f"{API_BASE}/tracks/{track_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
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
