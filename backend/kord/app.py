from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from kord import db
from kord.config import Settings
from kord.engine import resolve_engine_version
from kord.models import Analysis
from kord.spotify import SCOPES, authorize_url, build_pkce_pair
from kord.theory.palette import build_palette
from kord.theory.qualities import NO_CHORD, hue_for
from kord.theory.roman import roman_numeral
from kord.theory.scales import note_name, scale_for, uses_sharps

CONFIDENCE_FLOOR = 0.35
KEY_CONFIDENCE_FLOOR = 0.6

_SUFFIX = {
    "major": "", "minor": "m", "major7": "maj7", "minor7": "m7",
    "dominant7": "7", "diminished": "dim", "augmented": "aug",
    "dim7": "dim7", "hdim7": "m7b5", "sus2": "sus2", "sus4": "sus4", "power": "5",
}


def chord_label(root: int, quality: str, prefer_sharps: bool = False) -> str:
    """Chord symbol spelled to match the key, so B major shows F# rather than Gb."""
    if root < 0 or quality == NO_CHORD:
        return "N.C."
    return f"{note_name(root, prefer_sharps)}{_SUFFIX.get(quality, '')}"


def render_analysis(analysis: Analysis) -> dict:
    """Shape an Analysis for the UI: chart, palette and theory from one record."""
    key = analysis.key
    sharps = uses_sharps(key.root, key.mode)
    chart = [
        {
            "start_s": round(segment.start_s, 3),
            "end_s": round(segment.end_s, 3),
            "label": chord_label(segment.root, segment.quality, sharps),
            "quality": segment.quality,
            "roman": roman_numeral(key.root, key.mode, segment.root, segment.quality),
            "hue": hue_for(segment.quality),
            # Spec section 10: uncertainty is shown, never hidden.
            "uncertain": segment.confidence < CONFIDENCE_FLOOR,
        }
        for segment in analysis.chord_segments
        if segment.quality != NO_CHORD and segment.root >= 0
    ]
    scale = scale_for(key.root, key.mode)
    return {
        "status": "done",
        "chart": chart,
        "palette": [{"hue": stop.hue, "weight": round(stop.weight, 4)}
                    for stop in build_palette(analysis.chord_segments)],
        "theory": {
            "key": scale.name,
            "key_uncertain": (not key.agreed) or key.confidence < KEY_CONFIDENCE_FLOOR,
            "tempo": round(analysis.tempo, 1),
            "scale": {"notes": scale.notes, "suggestions": scale.suggestions},
        },
        "flags": analysis.flags,
        "sync_offset_ms": analysis.sync_offset_ms,
    }


def build_app() -> FastAPI:
    """Production entrypoint: wires the real dependencies from the environment.

    `create_app` takes them injected so tests can supply fakes, which means it
    cannot be used as a zero-argument uvicorn factory. This is that factory:

        uvicorn kord.app:build_app --factory --port 8000
    """
    from kord.spotify import SpotifyClient

    settings = Settings.from_env()
    conn = db.connect(settings.db_path)
    db.init_schema(conn)
    return create_app(settings, SpotifyClient(settings.spotify_client_id), conn)


def _auth_problem(headline: str, detail: str) -> HTMLResponse:
    """A readable page for a browser, rather than a validation error blob."""
    return HTMLResponse(
        status_code=400,
        content=(
            "<!doctype html><meta charset=utf-8><title>Kord — sign-in</title>"
            "<style>body{background:#0b0d10;color:#e8e6e1;font:16px/1.5 "
            "ui-sans-serif,system-ui,sans-serif;margin:0;display:grid;"
            "place-items:center;min-height:100vh}main{max-width:44ch;padding:2rem}"
            "h1{font-size:1.3rem;margin:0 0 .75rem}p{color:#8a8f98;margin:0 0 .75rem}"
            "code{color:#c8a24a;font-family:ui-monospace,monospace;font-size:.9em}"
            "a{color:#c8a24a}</style>"
            f"<main><h1>{headline}</h1><p>{detail}</p></main>"
        ),
    )


def create_app(settings: Settings, spotify, conn) -> FastAPI:
    app = FastAPI(title="Kord")
    app.state.access_token = None
    app.state.verifier = None
    engine_version = resolve_engine_version(settings)

    def require_token() -> str:
        if not app.state.access_token:
            raise HTTPException(status_code=401, detail="not authenticated")
        return app.state.access_token

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "engine": engine_version}

    @app.get("/api/auth/status")
    async def auth_status():
        return {"authenticated": bool(app.state.access_token)}

    @app.get("/api/auth/login")
    async def login():
        verifier, challenge = build_pkce_pair()
        app.state.verifier = verifier
        return RedirectResponse(authorize_url(
            settings.spotify_client_id, settings.redirect_uri, challenge, SCOPES))

    @app.get("/api/auth/callback")
    async def callback(code: str | None = None, error: str | None = None):
        # Spotify sends people here, but so does a stale tab or a hand-typed URL.
        # A human is reading this page in a browser, so explain rather than 422.
        if error:
            return _auth_problem(
                f"Spotify returned an error: <code>{error}</code>.",
                "If it says the redirect URI is invalid, the URI registered in "
                "your Spotify app must exactly match "
                f"<code>{settings.redirect_uri}</code> — including "
                "<code>127.0.0.1</code> rather than <code>localhost</code>.")
        if not code:
            return _auth_problem(
                "This page is the end of the Spotify sign-in, not the start.",
                "Nothing to do here directly — begin at "
                '<a href="/api/auth/login">/api/auth/login</a>.')
        if not app.state.verifier:
            return _auth_problem(
                "This sign-in attempt has expired.",
                "The security code is held in memory and is lost when the server "
                'restarts. Start again at <a href="/api/auth/login">'
                "/api/auth/login</a>.")

        tokens = await spotify.exchange_code(
            code, app.state.verifier, settings.redirect_uri)
        app.state.access_token = tokens["access_token"]
        if tokens.get("refresh_token"):
            conn.execute(
                """INSERT INTO auth (id, refresh_token, scopes) VALUES (1, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET refresh_token=excluded.refresh_token""",
                (tokens["refresh_token"], SCOPES))
            conn.commit()
        return RedirectResponse(settings.ui_url)

    @app.get("/api/search")
    async def search(q: str = Query(min_length=1)):
        return await spotify.search_tracks(q, require_token())

    @app.get("/api/track/{track_id}")
    async def get_track(track_id: str):
        track = await spotify.get_track(track_id, require_token())
        db.upsert_track(conn, track["id"], track["artist"], track["title"],
                        track["album"], track["duration_ms"])

        analysis = db.get_analysis(conn, track_id, engine_version)
        if analysis is not None:
            return {"track": track, **render_analysis(analysis)}

        job = conn.execute(
            "SELECT state, error FROM job WHERE spotify_id=? ORDER BY id DESC LIMIT 1",
            (track_id,)).fetchone()
        if job is None or job["state"] == "done":
            db.enqueue_job(conn, track_id)
            return {"track": track, "status": "pending"}
        if job["state"] in ("failed", "unavailable"):
            return {"track": track, "status": job["state"], "error": job["error"]}
        return {"track": track, "status": "pending"}

    @app.post("/api/track/{track_id}/analyze")
    async def analyze(track_id: str):
        return {"job_id": db.enqueue_job(conn, track_id), "status": "pending"}

    @app.get("/api/track/{track_id}/events")
    async def events(track_id: str):
        async def stream():
            while True:
                if db.get_analysis(conn, track_id, engine_version) is not None:
                    yield f"data: {json.dumps({'status': 'done'})}\n\n"
                    return
                row = conn.execute(
                    "SELECT state, error FROM job WHERE spotify_id=? "
                    "ORDER BY id DESC LIMIT 1", (track_id,)).fetchone()
                state = row["state"] if row else "pending"
                payload = {"status": state}
                if row and row["error"]:
                    payload["error"] = row["error"]
                yield f"data: {json.dumps(payload)}\n\n"
                if state in ("failed", "unavailable"):
                    return
                await asyncio.sleep(2)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app
