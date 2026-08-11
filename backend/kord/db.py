from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from kord.models import Analysis

SCHEMA = """
CREATE TABLE IF NOT EXISTS track (
    spotify_id   TEXT PRIMARY KEY,
    artist       TEXT NOT NULL,
    title        TEXT NOT NULL,
    album        TEXT,
    duration_ms  INTEGER NOT NULL,
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
    refresh_token TEXT NOT NULL,
    scopes        TEXT NOT NULL,
    obtained_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


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
