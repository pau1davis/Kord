from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import (
    FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse,
)

from kord import db
from kord.audio.stem_store import StemStore
from kord.audio.stems import STEM_NAMES
from kord.audio.store import AudioStore
from kord.config import Settings
from kord.engine import resolve_engine_version
from kord.models import Analysis
from kord.spotify import SCOPES, SpotifyError, authorize_url, build_pkce_pair
from kord.theory.palette import build_palette
from kord.theory.library import summarise
from kord.theory.taste import aggregate_palette
from kord.theory.qualities import NO_CHORD, hue_for
from kord.theory.roman import roman_numeral
from kord.theory.scales import note_name, scale_for, uses_sharps

CONFIDENCE_FLOOR = 0.35
KEY_CONFIDENCE_FLOOR = 0.6

# mimetypes maps .m4a to audio/mp4a-latm (LATM-packaged AAC, which browsers
# refuse) and .webm to video/webm. Both are wrong for what we serve, so the
# type is pinned here rather than guessed.
AUDIO_MEDIA_TYPES = {
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".webm": "audio/webm",
    ".opus": "audio/ogg",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
}

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


def render_analysis(analysis: Analysis, has_audio: bool = False) -> dict:
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
                    for stop in build_palette(analysis.chord_segments, analysis.heaviness)],
        "theory": {
            "key": scale.name,
            "key_uncertain": (not key.agreed) or key.confidence < KEY_CONFIDENCE_FLOOR,
            "tempo": round(analysis.tempo, 1),
            "scale": {"notes": scale.notes, "suggestions": scale.suggestions},
        },
        "heaviness": round(analysis.heaviness, 3),
        "flags": analysis.flags,
        "sync_offset_ms": analysis.sync_offset_ms,
        "sections": [
            {"start_s": round(s.start_s, 3), "end_s": round(s.end_s, 3), "label": s.label}
            for s in analysis.sections
        ],
        "has_audio": has_audio,
        "beats": analysis.beat_grid.times_s,
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
    app.state.verifier = None
    engine_version = resolve_engine_version(settings)

    # Restore the previous session, so restarting the server does not sign the
    # user out. Only the PKCE verifier is genuinely per-process.
    session = db.load_session(conn)
    app.state.access_token = None if session is None or session["expired"] else session["access_token"]

    async def require_token() -> str:
        # app.state.access_token is only a cache for /api/auth/status. Expiry
        # lives in load_session, so ask it every time: a token cached while it
        # was valid is otherwise served long after it dies, and every Spotify
        # call 401s until the process happens to restart.
        stored = db.load_session(conn)
        if stored and not stored["expired"]:
            app.state.access_token = stored["access_token"]
            return app.state.access_token

        if stored and stored["refresh_token"]:
            try:
                tokens = await spotify.refresh(stored["refresh_token"])
            except SpotifyError:
                raise HTTPException(
                    status_code=401,
                    detail="Your Spotify session expired. Connect again.") from None
            app.state.access_token = tokens["access_token"]
            db.save_session(
                conn, tokens["access_token"], tokens.get("refresh_token"),
                tokens.get("expires_in", 3600), SCOPES)
            return app.state.access_token

        raise HTTPException(
            status_code=401, detail="Connect your Spotify account to search.")

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "engine": engine_version}

    @app.get("/api/auth/status")
    async def auth_status():
        # "Can we actually call Spotify?", not "is a token cached?". A cached
        # token that has since expired would otherwise report connected while
        # every search 401s, and a refreshable session would report signed out.
        session = db.load_session(conn)
        usable = bool(
            session and (not session["expired"] or session["refresh_token"]))
        return {"authenticated": usable}

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
        db.save_session(
            conn, tokens["access_token"], tokens.get("refresh_token"),
            tokens.get("expires_in", 3600), SCOPES)
        return RedirectResponse(settings.ui_url)

    @app.exception_handler(SpotifyError)
    async def spotify_error_handler(request, exc: SpotifyError):
        # Pass Spotify's own words through. A bare 500 tells the user nothing,
        # and the UI cannot distinguish "your session expired" from "we broke".
        status = 401 if exc.status in (401, 403) else 502
        return JSONResponse(
            status_code=status,
            content={"detail": exc.message, "spotify_status": exc.status},
        )

    @app.get("/api/search")
    async def search(q: str = Query(min_length=1)):
        return await spotify.search_tracks(q, await require_token())

    @app.get("/api/me/top")
    async def me_top():
        return await spotify.top_tracks(await require_token())

    @app.get("/api/me/recent")
    async def me_recent():
        """What you were just listening to on Spotify, ready to learn."""
        return await spotify.recently_played(await require_token())

    @app.get("/api/me/library")
    async def me_library():
        """Kord's own state: what you have analysed and what you were last on.

        Deliberately local — no Spotify call, so the home screen has something
        real to show even when the network or the token is having a bad day.
        """
        analyses = []
        for row in conn.execute("SELECT spotify_id FROM analysis WHERE engine_version=?",
                                (engine_version,)):
            found = db.get_analysis(conn, row["spotify_id"], engine_version)
            if found is not None:
                analyses.append(found)

        opened = db.recently_opened(conn, limit=1)
        resume = None
        if opened:
            row = opened[0]
            found = db.get_analysis(conn, row["spotify_id"], engine_version)
            resume = {
                "id": row["spotify_id"],
                "title": row["title"],
                "artist": row["artist"],
                "key": scale_for(found.key.root, found.key.mode).name if found else None,
                "tempo": round(found.tempo) if found else None,
            }

        summary = summarise(analyses)
        summary["with_audio"] = db.count_tracks_with_audio(conn)
        summary["with_stems"] = conn.execute(
            "SELECT COUNT(*) c FROM stem_job WHERE state='done'").fetchone()["c"]
        summary["resume"] = resume
        return summary

    @app.get("/api/me/taste")
    async def me_taste():
        """Palette over the top tracks already analysed, plus how far along
        the background analysis is. Deliberately does not wait for it."""
        tracks = await spotify.top_tracks(await require_token())
        analyses = []
        for track in tracks:
            found = db.get_analysis(conn, track["id"], engine_version)
            if found is not None:
                analyses.append(found)
        return {
            "palette": [
                {"hue": stop.hue, "weight": stop.weight}
                for stop in aggregate_palette(analyses)
            ],
            "analyzed": len(analyses),
            "total": len(tracks),
        }

    @app.post("/api/me/top/analyze")
    async def analyze_top():
        """Queue whatever is not analysed yet.

        enqueue_job already reuses a pending job for the same song, so calling
        this repeatedly is safe and costs nothing.
        """
        tracks = await spotify.top_tracks(await require_token())
        queued = 0
        for track in tracks:
            db.upsert_track(
                conn, track["id"], track["artist"], track["title"],
                track["album"], track["duration_ms"])
            if db.get_analysis(conn, track["id"], engine_version) is None:
                db.enqueue_job(conn, track["id"])
                queued += 1
        return {"queued": queued, "total": len(tracks)}

    @app.get("/api/track/{track_id}")
    async def get_track(track_id: str):
        track = await spotify.get_track(track_id, await require_token())
        db.upsert_track(conn, track["id"], track["artist"], track["title"],
                        track["album"], track["duration_ms"])

        analysis = db.get_analysis(conn, track_id, engine_version)
        if analysis is not None:
            store = AudioStore(settings.audio_dir, settings.audio_cap_bytes)
            has_audio = store.path_for(track_id) is not None
            return {"track": track, **render_analysis(analysis, has_audio)}

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

    @app.get("/api/track/{track_id}/audio")
    async def audio(track_id: str):
        """Serve retained audio. FileResponse handles Range requests, which the
        browser needs for seeking — without 206 the scrubber and looping break."""
        store = AudioStore(settings.audio_dir, settings.audio_cap_bytes)
        path = store.path_for(track_id)
        if path is None:
            raise HTTPException(status_code=404, detail="audio not retained")
        db.touch_played(conn, track_id)
        return FileResponse(
            path,
            media_type=AUDIO_MEDIA_TYPES.get(
                path.suffix.lower(), "application/octet-stream"),
        )

    @app.post("/api/track/{track_id}/stems")
    async def request_stems(track_id: str):
        return {"job_id": db.enqueue_stem_job(conn, track_id), "status": "pending"}

    @app.get("/api/track/{track_id}/stems")
    async def stem_status(track_id: str):
        store = StemStore(settings.stems_dir)
        job = db.stem_job_for(conn, track_id)
        available = [
            name for name in STEM_NAMES
            if store.path_for(track_id, name) is not None
        ]
        return {
            "status": job["state"] if job else "none",
            "error": job["error"] if job else None,
            "progress": job["progress"] if job else 0,
            "available": available,
        }

    @app.get("/api/track/{track_id}/stems/{stem}")
    async def stem_file(track_id: str, stem: str):
        path = StemStore(settings.stems_dir).path_for(track_id, stem)
        if path is None:
            raise HTTPException(status_code=404, detail="stem not available")
        return FileResponse(path, media_type=AUDIO_MEDIA_TYPES[".m4a"])

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
