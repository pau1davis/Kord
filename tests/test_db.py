import pytest

from kord import db
from kord.models import Analysis, BeatGrid, ChordSegment, KeyEstimate


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_schema(c)
    return c


def make_analysis(spotify_id="t1", engine_version="chroma-1"):
    return Analysis(
        spotify_id=spotify_id, engine_version=engine_version,
        key=KeyEstimate(0, "major", 0.8, True), tempo=120.0,
        beat_grid=BeatGrid([0.0, 0.5], 120.0),
        chord_segments=[ChordSegment(0.0, 2.0, 0, "major", 0.9)],
        source_url="https://example.invalid/x", source_duration_ms=180000,
        time_scale=1.0, sync_offset_ms=0, flags=[], chord_confidence_mean=0.9,
    )


def test_save_and_get_analysis_roundtrip(conn):
    db.upsert_track(conn, "t1", "Artist", "Title", "Album", 180000)
    db.save_analysis(conn, make_analysis())
    got = db.get_analysis(conn, "t1", "chroma-1")
    assert got.chord_segments[0].quality == "major"
    assert got.key.root == 0


def test_engine_version_bump_invalidates_cache(conn):
    db.upsert_track(conn, "t1", "Artist", "Title", "Album", 180000)
    db.save_analysis(conn, make_analysis(engine_version="chroma-1"))
    assert db.get_analysis(conn, "t1", "btc-1") is None      # different engine, cache miss
    assert db.get_analysis(conn, "t1", "chroma-1") is not None


def test_both_engine_versions_can_coexist(conn):
    db.upsert_track(conn, "t1", "Artist", "Title", "Album", 180000)
    db.save_analysis(conn, make_analysis(engine_version="chroma-1"))
    db.save_analysis(conn, make_analysis(engine_version="btc-1"))
    assert db.get_analysis(conn, "t1", "chroma-1") is not None
    assert db.get_analysis(conn, "t1", "btc-1") is not None


def test_resaving_replaces_rather_than_duplicating(conn):
    db.upsert_track(conn, "t1", "Artist", "Title", "Album", 180000)
    db.save_analysis(conn, make_analysis())
    db.save_analysis(conn, make_analysis())
    rows = conn.execute("SELECT COUNT(*) FROM analysis").fetchone()[0]
    assert rows == 1


def test_upsert_track_updates_metadata_without_duplicating(conn):
    db.upsert_track(conn, "t1", "Old", "Title", "Album", 180000)
    db.upsert_track(conn, "t1", "New", "Title", "Album", 190000)
    row = conn.execute("SELECT artist, duration_ms FROM track").fetchone()
    assert row["artist"] == "New"
    assert row["duration_ms"] == 190000
    assert conn.execute("SELECT COUNT(*) FROM track").fetchone()[0] == 1


def test_enqueue_is_idempotent_for_pending_jobs(conn):
    db.upsert_track(conn, "t1", "Artist", "Title", "Album", 180000)
    first = db.enqueue_job(conn, "t1")
    second = db.enqueue_job(conn, "t1")
    assert first == second


def test_claim_job_returns_pending_then_nothing(conn):
    db.upsert_track(conn, "t1", "Artist", "Title", "Album", 180000)
    db.enqueue_job(conn, "t1")
    job = db.claim_job(conn)
    assert job["spotify_id"] == "t1"
    assert db.claim_job(conn) is None      # already running, not re-claimed


def test_claim_job_increments_attempts(conn):
    db.upsert_track(conn, "t1", "Artist", "Title", "Album", 180000)
    job_id = db.enqueue_job(conn, "t1")
    db.claim_job(conn)
    assert conn.execute(
        "SELECT attempts FROM job WHERE id=?", (job_id,)).fetchone()["attempts"] == 1


def test_finish_job_records_error(conn):
    db.upsert_track(conn, "t1", "Artist", "Title", "Album", 180000)
    job_id = db.enqueue_job(conn, "t1")
    db.claim_job(conn)
    db.finish_job(conn, job_id, "failed", "no audio candidate")
    row = conn.execute("SELECT state, error FROM job WHERE id=?", (job_id,)).fetchone()
    assert row["state"] == "failed"
    assert row["error"] == "no audio candidate"


def test_init_schema_is_idempotent(conn):
    db.init_schema(conn)      # second run must not raise
    db.upsert_track(conn, "t1", "Artist", "Title", "Album", 180000)
    assert conn.execute("SELECT COUNT(*) FROM track").fetchone()[0] == 1


def test_session_survives_a_restart(conn):
    """The access token lived only in memory, so every restart logged the user out."""
    db.save_session(conn, access_token="at", refresh_token="rt", expires_in=3600)
    session = db.load_session(conn)
    assert session["access_token"] == "at"
    assert session["refresh_token"] == "rt"
    assert session["expired"] is False


def test_expired_session_is_reported_as_expired(conn):
    db.save_session(conn, access_token="at", refresh_token="rt", expires_in=-10)
    session = db.load_session(conn)
    assert session["expired"] is True
    assert session["refresh_token"] == "rt"      # still usable to get a new one


def test_no_session_returns_none(conn):
    assert db.load_session(conn) is None


def test_saving_again_replaces_the_previous_session(conn):
    db.save_session(conn, access_token="a1", refresh_token="r1", expires_in=3600)
    db.save_session(conn, access_token="a2", refresh_token="r2", expires_in=3600)
    assert db.load_session(conn)["access_token"] == "a2"
    assert conn.execute("SELECT COUNT(*) FROM auth").fetchone()[0] == 1


def test_a_refresh_without_a_new_refresh_token_keeps_the_old_one(conn):
    """Spotify often omits refresh_token on refresh; losing it would end the session."""
    db.save_session(conn, access_token="a1", refresh_token="r1", expires_in=3600)
    db.save_session(conn, access_token="a2", refresh_token=None, expires_in=3600)
    assert db.load_session(conn)["refresh_token"] == "r1"


def test_a_refresh_token_alone_is_still_a_usable_session(conn):
    """Rows written before access tokens were persisted still hold a refresh token.

    Returning None for those would strand the user on a re-login loop when a
    refresh would have restored them silently.
    """
    conn.execute("INSERT INTO auth (id, refresh_token, scopes) VALUES (1, 'rt', 's')")
    conn.commit()
    session = db.load_session(conn)
    assert session is not None
    assert session["refresh_token"] == "rt"
    assert session["access_token"] is None
    assert session["expired"] is True      # nothing usable without refreshing first


def test_migrates_a_legacy_auth_table_with_not_null_refresh_token():
    """The original schema declared refresh_token NOT NULL.

    Spotify usually omits refresh_token when refreshing, so that constraint
    turns a successful refresh into an IntegrityError. CREATE TABLE IF NOT
    EXISTS never alters an existing table, so the column must be rebuilt.
    """
    c = db.connect(":memory:")
    c.executescript(
        """CREATE TABLE auth (
               id INTEGER PRIMARY KEY CHECK (id = 1),
               refresh_token TEXT NOT NULL,
               scopes TEXT NOT NULL,
               obtained_at TEXT NOT NULL DEFAULT (datetime('now')));
           INSERT INTO auth (id, refresh_token, scopes) VALUES (1, 'legacy', 'sc');"""
    )
    c.commit()

    db.init_schema(c)

    # The stored refresh token survives the rebuild...
    assert db.load_session(c)["refresh_token"] == "legacy"
    # ...and a refresh that returns no new refresh token now succeeds.
    db.save_session(c, access_token="at", refresh_token=None, expires_in=3600)
    session = db.load_session(c)
    assert session["access_token"] == "at"
    assert session["refresh_token"] == "legacy"
