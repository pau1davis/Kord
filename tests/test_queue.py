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


def test_completed_job_records_audio_ext_and_trims_to_cap(tmp_path, conn):
    """The pipeline never touches the database, so run_one_job is where the
    retained file's extension gets recorded and the cap gets enforced.

    A never-played pre-existing track ("aaa") plus what this job retains
    ("t1") together exceed the cap, so eviction must run. `audio_ext IS NULL`
    tracks sort first for eviction (never played = most evictable), and among
    ties it's alphabetical — "aaa" sorts before "t1" — so evicting "aaa"
    alone is enough to fit, and "t1" (this job's own track) survives. That
    lets the test check both effects cleanly: "aaa" trimmed away, and "t1"'s
    audio_ext durably recorded rather than immediately evicted back to NULL.
    """
    from kord.audio.store import AudioStore

    def write(path, size):
        path.write_bytes(b"x" * size)
        return path

    store = AudioStore(tmp_path / "audio", cap_bytes=200)

    db.upsert_track(conn, "aaa", "A", "Old", "Al", 1000)
    store.retain("aaa", write(tmp_path / "aaa.webm", 150))
    db.set_audio_ext(conn, "aaa", ".webm")

    class RetainingPipeline:
        audio_store = store

        def run(self, spotify_id, artist, title, duration_ms):
            store.retain(spotify_id, write(tmp_path / "new.webm", 100))
            return Analysis(
                spotify_id=spotify_id, engine_version="chroma-1",
                key=KeyEstimate(0, "major", 0.8, True), tempo=120.0,
                beat_grid=BeatGrid([0.0], 120.0),
                chord_segments=[ChordSegment(0.0, 1.0, 0, "major", 0.9)],
                source_url="u", source_duration_ms=180000, time_scale=1.0,
                sync_offset_ms=0, flags=[], chord_confidence_mean=0.9)

    db.enqueue_job(conn, "t1")
    assert run_one_job(conn, RetainingPipeline()) == "done"

    row = conn.execute("SELECT audio_ext FROM track WHERE spotify_id='t1'").fetchone()
    assert row["audio_ext"] == ".webm", "this job's own retained audio was recorded"
    assert store.path_for("aaa") is None, "the older, unplayed track was evicted to fit"
    assert store.total_bytes() <= 200


def test_no_audio_store_on_pipeline_means_no_bookkeeping(conn):
    """Fakes without an `audio_store` attribute (like OkPipeline) must not
    break the job — this is the "no retention configured" path."""
    db.enqueue_job(conn, "t1")
    assert run_one_job(conn, OkPipeline()) == "done"
    row = conn.execute("SELECT audio_ext FROM track WHERE spotify_id='t1'").fetchone()
    assert row["audio_ext"] is None
