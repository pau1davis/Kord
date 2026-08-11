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
