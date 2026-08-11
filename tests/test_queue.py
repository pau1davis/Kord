import pytest

from kord import db
from kord.analysis.pipeline import NoAudioFound
from kord.models import Analysis, BeatGrid, ChordSegment, KeyEstimate
from kord.queue import run_one_job


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_schema(c)
    db.upsert_track(c, "t1", "Artist", "Title", "Album", 180000)
    return c


class OkPipeline:
    def run(self, spotify_id, artist, title, duration_ms):
        return Analysis(
            spotify_id=spotify_id, engine_version="chroma-1",
            key=KeyEstimate(0, "major", 0.8, True), tempo=120.0,
            beat_grid=BeatGrid([0.0], 120.0),
            chord_segments=[ChordSegment(0.0, 1.0, 0, "major", 0.9)],
            source_url="u", source_duration_ms=180000, time_scale=1.0,
            sync_offset_ms=0, flags=[], chord_confidence_mean=0.9)


class FailPipeline:
    def run(self, *args):
        raise NoAudioFound("nothing matched")


def test_successful_job_saves_analysis_and_marks_done(conn):
    db.enqueue_job(conn, "t1")
    assert run_one_job(conn, OkPipeline()) == "done"
    assert db.get_analysis(conn, "t1", "chroma-1") is not None
    assert conn.execute("SELECT state FROM job").fetchone()["state"] == "done"


def test_no_audio_marks_unavailable_with_reason(conn):
    db.enqueue_job(conn, "t1")
    assert run_one_job(conn, FailPipeline()) == "unavailable"
    row = conn.execute("SELECT state, error FROM job").fetchone()
    assert row["state"] == "unavailable"
    assert "nothing matched" in row["error"]


def test_unexpected_error_marks_failed_not_unavailable(conn):
    class Boom:
        def run(self, *args):
            raise RuntimeError("out of memory")

    db.enqueue_job(conn, "t1")
    assert run_one_job(conn, Boom()) == "failed"
    row = conn.execute("SELECT state, error FROM job").fetchone()
    assert row["state"] == "failed"
    assert "RuntimeError" in row["error"]


def test_unavailable_and_failed_are_distinguished(conn):
    """They mean different things to the user: 'no audio exists' vs 'we broke'."""
    db.enqueue_job(conn, "t1")
    assert run_one_job(conn, FailPipeline()) == "unavailable"
    db.upsert_track(conn, "t2", "A", "B", "C", 1000)
    db.enqueue_job(conn, "t2")

    class Boom:
        def run(self, *args):
            raise ValueError("bad")

    assert run_one_job(conn, Boom()) == "failed"


def test_missing_track_metadata_fails_cleanly(conn):
    conn.execute("INSERT INTO job (spotify_id) VALUES ('ghost')")
    conn.commit()
    assert run_one_job(conn, OkPipeline()) == "failed"
    row = conn.execute("SELECT error FROM job WHERE spotify_id='ghost'").fetchone()
    assert "metadata" in row["error"]


def test_empty_queue_returns_none(conn):
    assert run_one_job(conn, OkPipeline()) is None


def test_worker_never_propagates_pipeline_exceptions(conn):
    """The API process must survive anything the analyzer does."""
    class Nuclear:
        def run(self, *args):
            raise MemoryError("8GB exhausted")

    db.enqueue_job(conn, "t1")
    assert run_one_job(conn, Nuclear()) == "failed"      # returns, does not raise
