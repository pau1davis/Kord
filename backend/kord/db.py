from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from kord.models import Analysis

SCHEMA = """
CREATE TABLE IF NOT EXISTS track (
    spotify_id   TEXT PRIMARY KEY,
    artist       TEXT NOT NULL,
    title        TEXT NOT NULL,
    album        TEXT,
    duration_ms  INTEGER NOT NULL,
    audio_ext    TEXT,
    last_played_at TEXT,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS analysis (
    spotify_id     TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    payload        TEXT NOT NULL,
    analyzed_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (spotify_id, engine_version)
);
CREATE TABLE IF NOT EXISTS job (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    spotify_id TEXT NOT NULL,
    state      TEXT NOT NULL DEFAULT 'pending',
    attempts   INTEGER NOT NULL DEFAULT 0,
    error      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS job_state_idx ON job(state);
CREATE TABLE IF NOT EXISTS auth (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    refresh_token TEXT,
    access_token  TEXT,
    expires_at    REAL,
    scopes        TEXT,
    obtained_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS stem_job (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    spotify_id TEXT NOT NULL,
    state      TEXT NOT NULL DEFAULT 'pending',
    error      TEXT,
    progress   REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS stem_job_state_idx ON stem_job(state);
CREATE TABLE IF NOT EXISTS tab_job (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    spotify_id TEXT NOT NULL,
    state      TEXT NOT NULL DEFAULT 'pending',
    error      TEXT,
    progress   REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS tab_job_state_idx ON tab_job(state);
"""

# Columns added after the first release; ALTER is idempotent-checked below.
_AUTH_COLUMNS = {"access_token": "TEXT", "expires_at": "REAL"}
_TRACK_COLUMNS = {"audio_ext": "TEXT", "last_played_at": "TEXT"}
_STEM_JOB_COLUMNS = {"progress": "REAL NOT NULL DEFAULT 0"}


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate_auth(conn)
    _migrate_track(conn)
    _migrate_stem_job(conn)
    conn.commit()


def _migrate_stem_job(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(stem_job)")}
    for column, kind in _STEM_JOB_COLUMNS.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE stem_job ADD COLUMN {column} {kind}")


def _migrate_track(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(track)")}
    for column, kind in _TRACK_COLUMNS.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE track ADD COLUMN {column} {kind}")


def _migrate_auth(conn: sqlite3.Connection) -> None:
    """Bring an existing auth table up to the current shape.

    The first release declared `refresh_token TEXT NOT NULL`. Spotify usually
    omits refresh_token when refreshing, so that constraint turns a successful
    refresh into an IntegrityError. SQLite cannot drop NOT NULL in place and
    CREATE TABLE IF NOT EXISTS leaves existing tables untouched, so the table is
    rebuilt when the old constraint is present.
    """
    columns = {row["name"]: row for row in conn.execute("PRAGMA table_info(auth)")}
    if not columns:
        return

    if columns["refresh_token"]["notnull"]:
        conn.executescript(
            """ALTER TABLE auth RENAME TO auth_legacy;
               CREATE TABLE auth (
                   id            INTEGER PRIMARY KEY CHECK (id = 1),
                   refresh_token TEXT,
                   access_token  TEXT,
                   expires_at    REAL,
                   scopes        TEXT,
                   obtained_at   TEXT NOT NULL DEFAULT (datetime('now'))
               );
               INSERT INTO auth (id, refresh_token, scopes)
                   SELECT id, refresh_token, scopes FROM auth_legacy;
               DROP TABLE auth_legacy;"""
        )
        return

    for column, kind in _AUTH_COLUMNS.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE auth ADD COLUMN {column} {kind}")


def save_session(
    conn,
    access_token: str,
    refresh_token: str | None,
    expires_in: int,
    scopes: str = "",
) -> None:
    """Persist the session so a restart does not sign the user out.

    Spotify frequently omits `refresh_token` when refreshing, so an absent value
    means "keep the one we have" rather than "clear it".
    """
    expires_at = time.time() + expires_in
    conn.execute(
        """INSERT INTO auth (id, refresh_token, access_token, expires_at, scopes)
           VALUES (1, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             refresh_token=COALESCE(excluded.refresh_token, auth.refresh_token),
             access_token=excluded.access_token,
             expires_at=excluded.expires_at,
             scopes=COALESCE(NULLIF(excluded.scopes, ''), auth.scopes),
             obtained_at=datetime('now')""",
        (refresh_token, access_token, expires_at, scopes),
    )
    conn.commit()


def load_session(conn) -> dict | None:
    row = conn.execute(
        "SELECT refresh_token, access_token, expires_at, scopes FROM auth WHERE id=1"
    ).fetchone()
    if row is None or not (row["access_token"] or row["refresh_token"]):
        return None
    # A refresh token alone is still a session — it just needs refreshing first.
    # Treat an access token as expired a minute early, so a call cannot start on
    # one that dies mid-flight.
    expired = (
        not row["access_token"]
        or (row["expires_at"] or 0) - 60 <= time.time()
    )
    return {
        "access_token": row["access_token"],
        "refresh_token": row["refresh_token"],
        "scopes": row["scopes"],
        "expired": expired,
    }


def upsert_track(conn, spotify_id, artist, title, album, duration_ms) -> None:
    conn.execute(
        """INSERT INTO track (spotify_id, artist, title, album, duration_ms)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(spotify_id) DO UPDATE SET
             artist=excluded.artist, title=excluded.title,
             album=excluded.album, duration_ms=excluded.duration_ms""",
        (spotify_id, artist, title, album, duration_ms),
    )
    conn.commit()


def save_analysis(conn, analysis: Analysis) -> None:
    conn.execute(
        """INSERT INTO analysis (spotify_id, engine_version, payload)
           VALUES (?, ?, ?)
           ON CONFLICT(spotify_id, engine_version) DO UPDATE SET
             payload=excluded.payload, analyzed_at=datetime('now')""",
        (analysis.spotify_id, analysis.engine_version, json.dumps(analysis.to_dict())),
    )
    conn.commit()


def get_analysis(conn, spotify_id: str, engine_version: str) -> Analysis | None:
    """Cache lookup is keyed by engine version, so improving the analyzer
    invalidates stale results rather than silently mixing engine outputs."""
    row = conn.execute(
        "SELECT payload FROM analysis WHERE spotify_id=? AND engine_version=?",
        (spotify_id, engine_version),
    ).fetchone()
    return Analysis.from_dict(json.loads(row["payload"])) if row else None


def best_analysis(
    conn, spotify_id: str, engine_version: str
) -> tuple[Analysis | None, bool]:
    """The current engine's analysis, or the newest older one. Plus whether it
    is current.

    Keying the cache by engine version is right — mixing engine outputs would
    be worse — but treating a miss as "no analysis" made every bump destructive.
    Going to btc-5 put 25 songs that had worked an hour earlier into
    "unavailable", and the re-analysis meant to fix them was being refused by
    YouTube with 403s, so they would have stayed there.

    An older analysis is worth strictly more than nothing: it is what the app
    was showing yesterday. The caller upgrades it in the background and says
    which engine it came from.
    """
    current = get_analysis(conn, spotify_id, engine_version)
    if current is not None:
        return current, True
    row = conn.execute(
        "SELECT payload FROM analysis WHERE spotify_id=? "
        "ORDER BY analyzed_at DESC, rowid DESC LIMIT 1",
        (spotify_id,),
    ).fetchone()
    if row is None:
        return None, False
    return Analysis.from_dict(json.loads(row["payload"])), False


def enqueue_job(conn, spotify_id: str) -> int:
    existing = conn.execute(
        "SELECT id FROM job WHERE spotify_id=? AND state IN ('pending','running')",
        (spotify_id,),
    ).fetchone()
    if existing:
        return existing["id"]
    cursor = conn.execute("INSERT INTO job (spotify_id) VALUES (?)", (spotify_id,))
    conn.commit()
    return cursor.lastrowid


def claim_job(conn) -> sqlite3.Row | None:
    row = conn.execute(
        "SELECT * FROM job WHERE state='pending' ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    conn.execute(
        """UPDATE job SET state='running', attempts=attempts+1,
           updated_at=datetime('now') WHERE id=?""",
        (row["id"],),
    )
    conn.commit()
    return row


def finish_job(conn, job_id: int, state: str, error: str | None = None) -> None:
    conn.execute(
        "UPDATE job SET state=?, error=?, updated_at=datetime('now') WHERE id=?",
        (state, error, job_id),
    )
    conn.commit()


def set_audio_ext(conn, spotify_id: str, ext: str | None) -> None:
    conn.execute("UPDATE track SET audio_ext=? WHERE spotify_id=?", (ext, spotify_id))
    conn.commit()


def touch_played(conn, spotify_id: str) -> None:
    """Record a play, so eviction can order by least recently played.

    Timestamps are computed in Python, not with SQLite's `datetime('now')`:
    that function only has second resolution (and `strftime(..., '%f')` tops
    out around milliseconds), so two plays in quick succession — as in the
    eviction test, and plausibly a real skip-back-and-replay in the UI — can
    tie and fall back to sorting by spotify_id, silently breaking recency
    order. `datetime.now()` gives microsecond resolution, which does not.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    conn.execute(
        "UPDATE track SET last_played_at=? WHERE spotify_id=?",
        (now, spotify_id),
    )
    conn.commit()


def audio_tracks_by_least_recently_played(conn) -> list[sqlite3.Row]:
    """Tracks holding audio, oldest play first. Never-played sorts first."""
    return list(conn.execute(
        """SELECT spotify_id, audio_ext FROM track
           WHERE audio_ext IS NOT NULL
           ORDER BY last_played_at IS NOT NULL, last_played_at ASC, spotify_id"""
    ))


def enqueue_stem_job(conn, spotify_id: str) -> int:
    """Queue separation, reusing any job that has not finished yet."""
    row = conn.execute(
        "SELECT id FROM stem_job WHERE spotify_id=? AND state IN "
        "('pending','running') ORDER BY id DESC LIMIT 1",
        (spotify_id,),
    ).fetchone()
    if row is not None:
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO stem_job (spotify_id) VALUES (?)", (spotify_id,))
    conn.commit()
    return cursor.lastrowid


def claim_stem_job(conn):
    row = conn.execute(
        "SELECT * FROM stem_job WHERE state='pending' ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    conn.execute(
        "UPDATE stem_job SET state='running', updated_at=datetime('now') "
        "WHERE id=?", (row["id"],))
    conn.commit()
    return row


def set_stem_progress(conn, job_id: int, fraction: float) -> None:
    conn.execute(
        "UPDATE stem_job SET progress=?, updated_at=datetime('now') WHERE id=?",
        (max(0.0, min(1.0, fraction)), job_id))
    conn.commit()


def finish_stem_job(conn, job_id: int, state: str, error: str | None = None) -> None:
    # Completing the progress too: a finished job still reading 87% looks like
    # it is still working.
    conn.execute(
        "UPDATE stem_job SET state=?, error=?, progress=1.0, "
        "updated_at=datetime('now') WHERE id=?", (state, error, job_id))
    conn.commit()


def stem_job_for(conn, spotify_id: str):
    return conn.execute(
        "SELECT * FROM stem_job WHERE spotify_id=? ORDER BY id DESC LIMIT 1",
        (spotify_id,),
    ).fetchone()


def recently_opened(conn, limit: int = 6):
    """Songs you have actually played in Kord, most recent first.

    `last_played_at` is stamped when the audio endpoint serves a file, so this
    is what you were working on rather than what you merely searched for.
    """
    return conn.execute(
        "SELECT * FROM track WHERE last_played_at IS NOT NULL "
        "ORDER BY last_played_at DESC LIMIT ?", (limit,)
    ).fetchall()


def count_tracks_with_audio(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) c FROM track WHERE audio_ext IS NOT NULL"
    ).fetchone()["c"]


def enqueue_tab_job(conn, spotify_id: str) -> int:
    """Queue transcription, reusing any job that has not finished yet."""
    row = conn.execute(
        "SELECT id FROM tab_job WHERE spotify_id=? AND state IN "
        "('pending','running') ORDER BY id DESC LIMIT 1",
        (spotify_id,),
    ).fetchone()
    if row is not None:
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO tab_job (spotify_id) VALUES (?)", (spotify_id,))
    conn.commit()
    return cursor.lastrowid


def claim_tab_job(conn):
    row = conn.execute(
        "SELECT * FROM tab_job WHERE state='pending' ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    conn.execute(
        "UPDATE tab_job SET state='running', updated_at=datetime('now') "
        "WHERE id=?", (row["id"],))
    conn.commit()
    return row


def set_tab_progress(conn, job_id: int, fraction: float) -> None:
    conn.execute(
        "UPDATE tab_job SET progress=?, updated_at=datetime('now') WHERE id=?",
        (max(0.0, min(1.0, fraction)), job_id))
    conn.commit()


def finish_tab_job(conn, job_id: int, state: str, error: str | None = None) -> None:
    # Completing the progress too: a finished job still reading 60% looks like
    # it is still working.
    conn.execute(
        "UPDATE tab_job SET state=?, error=?, progress=1.0, "
        "updated_at=datetime('now') WHERE id=?", (state, error, job_id))
    conn.commit()


def tab_job_for(conn, spotify_id: str):
    return conn.execute(
        "SELECT * FROM tab_job WHERE spotify_id=? ORDER BY id DESC LIMIT 1",
        (spotify_id,),
    ).fetchone()
