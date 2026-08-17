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

    A pre-existing never-played track ("aaa") plus what this job retains
    ("t1") together exceed the cap, so eviction must run. "aaa" is not the
    job's own track, so it's fair game and gets evicted to fit; "t1" is
    protected as the track just retained (see
    test_completed_job_never_evicts_the_track_it_just_retained for that
    protection exercised against the ordering that would otherwise pick the
    just-retained track first). This test checks both effects: "aaa" trimmed
    away, and "t1"'s audio_ext durably recorded rather than reverted to NULL.
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


def test_completed_job_never_evicts_the_track_it_just_retained(tmp_path, conn):
    """Regression: without protection, the just-retained track evicts itself.

    `db.audio_tracks_by_least_recently_played` sorts never-played tracks
    first, and the track this job just retained has no `last_played_at` yet.
    Retaining "aaa" while an already-played "zzz" occupies the store means
    the plain ordering would pick "aaa" — the job's own track — as the
    eviction candidate ahead of "zzz", deleting the file that was just
    written. In steady state (store at cap, everything else already played)
    that is not a corner case: it is the ordinary flow, and it would make
    every freshly analysed song 404 on playback forever, since there is no
    re-download path. "aaa" must survive; "zzz" must be evicted instead.
    """
    from kord.audio.store import AudioStore

    def write(path, size):
        path.write_bytes(b"x" * size)
        return path

    store = AudioStore(tmp_path / "audio", cap_bytes=200)

    db.upsert_track(conn, "zzz", "A", "Zzz", "Al", 1000)
    store.retain("zzz", write(tmp_path / "zzz.webm", 150))
    db.set_audio_ext(conn, "zzz", ".webm")
    db.touch_played(conn, "zzz")

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

    db.upsert_track(conn, "aaa", "A", "Aaa", "Al", 1000)
    db.enqueue_job(conn, "aaa")
    assert run_one_job(conn, RetainingPipeline()) == "done"

    row = conn.execute("SELECT audio_ext FROM track WHERE spotify_id='aaa'").fetchone()
    assert row["audio_ext"] == ".webm", "the job's own retained audio must survive"
    assert store.path_for("aaa") is not None
    assert store.path_for("zzz") is None, "the already-played track was evicted instead"


def test_no_audio_store_on_pipeline_means_no_bookkeeping(conn):
    """Fakes without an `audio_store` attribute (like OkPipeline) must not
    break the job — this is the "no retention configured" path."""
    db.enqueue_job(conn, "t1")
    assert run_one_job(conn, OkPipeline()) == "done"
    row = conn.execute("SELECT audio_ext FROM track WHERE spotify_id='t1'").fetchone()
    assert row["audio_ext"] is None


class FakeSeparator:
    """Writes a byte per stem. Demucs itself is never invoked in tests."""

    def __init__(self, explode=False):
        self.explode = explode
        self.calls = []

    def separate(self, source, dest_dir, on_progress=None):
        self.calls.append(source)
        if self.explode:
            raise RuntimeError("model exploded")
        dest_dir.mkdir(parents=True, exist_ok=True)
        written = {}
        for name in ("drums", "bass", "other", "vocals", "guitar", "piano"):
            p = dest_dir / f"{name}.m4a"
            p.write_bytes(b"x")
            written[name] = p
        return written


def _audio_store_with_song(tmp_path, conn):
    from kord.audio.store import AudioStore

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    (audio_dir / "t1.m4a").write_bytes(b"song")
    db.set_audio_ext(conn, "t1", ".m4a")
    return AudioStore(audio_dir, 10 * 1024 ** 3)


def test_stem_job_writes_every_stem(conn, tmp_path):
    from kord.audio.stem_store import StemStore
    from kord.queue import run_one_stem_job

    store = _audio_store_with_song(tmp_path, conn)
    stems = StemStore(tmp_path / "stems")
    db.enqueue_stem_job(conn, "t1")

    assert run_one_stem_job(conn, FakeSeparator(), store, stems) == "done"
    assert stems.has_stems("t1")
    assert stems.path_for("t1", "guitar") is not None


def test_stem_job_without_retained_audio_is_unavailable(conn, tmp_path):
    from kord.audio.stem_store import StemStore
    from kord.audio.store import AudioStore
    from kord.queue import run_one_stem_job

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    db.enqueue_stem_job(conn, "t1")

    state = run_one_stem_job(
        conn, FakeSeparator(), AudioStore(audio_dir, 10 * 1024 ** 3),
        StemStore(tmp_path / "stems"))
    assert state == "unavailable"
    assert "audio" in db.stem_job_for(conn, "t1")["error"]


def test_a_failing_separator_records_the_failure(conn, tmp_path):
    from kord.audio.stem_store import StemStore
    from kord.queue import run_one_stem_job

    store = _audio_store_with_song(tmp_path, conn)
    db.enqueue_stem_job(conn, "t1")

    state = run_one_stem_job(
        conn, FakeSeparator(explode=True), store, StemStore(tmp_path / "stems"))
    assert state == "failed"
    assert "exploded" in db.stem_job_for(conn, "t1")["error"]


def test_no_pending_stem_job_returns_none(conn, tmp_path):
    from kord.audio.stem_store import StemStore
    from kord.queue import run_one_stem_job

    store = _audio_store_with_song(tmp_path, conn)
    assert run_one_stem_job(
        conn, FakeSeparator(), store, StemStore(tmp_path / "stems")) is None


def test_stem_job_reports_progress_as_it_goes(conn, tmp_path):
    """A blind two-minute wait is the actual complaint, not the two minutes."""
    from kord.audio.stem_store import StemStore
    from kord.queue import run_one_stem_job

    class ReportingSeparator(FakeSeparator):
        def separate(self, source, dest_dir, on_progress=None):
            for fraction in (0.25, 0.5, 0.75):
                if on_progress:
                    on_progress(fraction)
            return super().separate(source, dest_dir)

    store = _audio_store_with_song(tmp_path, conn)
    job_id = db.enqueue_stem_job(conn, "t1")
    seen = []

    original = db.set_stem_progress

    def spy(c, jid, fraction):
        seen.append(fraction)
        original(c, jid, fraction)

    db.set_stem_progress = spy
    try:
        run_one_stem_job(conn, ReportingSeparator(), store,
                         StemStore(tmp_path / "stems"))
    finally:
        db.set_stem_progress = original

    assert seen == [0.25, 0.5, 0.75]
    assert db.stem_job_for(conn, "t1")["progress"] == 1.0
    assert job_id


def test_a_tab_job_transcribes_the_bass_and_saves_it(tmp_path, monkeypatch):
    """The join this task exists for: stems in, note events on disk."""
    import numpy as np
    import soundfile as sf

    from kord.audio.stem_store import StemStore
    from kord.queue import run_one_tab_job
    from kord.tab.events import NoteEvent
    from kord.tab.store import TabStore

    conn = db.connect(":memory:")
    db.init_schema(conn)

    stem_store = StemStore(tmp_path / "stems")
    stem_store.dir_for("t1").mkdir(parents=True)
    sr = 22050
    t = np.arange(sr) / sr
    # Contents are irrelevant — transcribe_bass is stubbed below. The file only
    # has to exist, because that is all StemStore.path_for checks.
    sf.write(stem_store.dir_for("t1") / "bass.m4a",
             np.sin(2 * np.pi * 110.0 * t).astype(np.float32), sr, format="WAV")

    tab_store = TabStore(tmp_path / "tabs")
    monkeypatch.setattr("kord.queue.transcribe_bass",
                        lambda path, **kw: [NoteEvent(0.0, 0.5, 45, 0.9)])
    db.enqueue_tab_job(conn, "t1")

    assert run_one_tab_job(conn, tab_store, stem_store) == "done"
    assert tab_store.load("t1", "bass") == [NoteEvent(0.0, 0.5, 45, 0.9)]
    assert db.tab_job_for(conn, "t1")["progress"] == 1.0


def test_a_tab_job_without_stems_is_unavailable_not_a_crash(tmp_path):
    from kord.audio.stem_store import StemStore
    from kord.queue import run_one_tab_job
    from kord.tab.store import TabStore

    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.enqueue_tab_job(conn, "t1")
    state = run_one_tab_job(
        conn, TabStore(tmp_path / "tabs"), StemStore(tmp_path / "stems"))
    assert state == "unavailable"
    assert "separate" in db.tab_job_for(conn, "t1")["error"].lower()


def test_an_idle_tab_queue_returns_none(tmp_path):
    from kord.audio.stem_store import StemStore
    from kord.queue import run_one_tab_job
    from kord.tab.store import TabStore

    conn = db.connect(":memory:")
    db.init_schema(conn)
    assert run_one_tab_job(
        conn, TabStore(tmp_path / "tabs"), StemStore(tmp_path / "stems")) is None


def test_a_failing_engine_records_the_error_and_does_not_raise(tmp_path, monkeypatch):
    """Transcription is an extra on top of a song that already works: a failure
    must leave the analysis, the audio and the stems untouched."""
    import numpy as np
    import soundfile as sf

    from kord.audio.stem_store import StemStore
    from kord.queue import run_one_tab_job
    from kord.tab.store import TabStore

    conn = db.connect(":memory:")
    db.init_schema(conn)
    stem_store = StemStore(tmp_path / "stems")
    stem_store.dir_for("t1").mkdir(parents=True)
    sf.write(stem_store.dir_for("t1") / "bass.m4a",
             np.zeros(22050, dtype=np.float32), 22050, format="WAV")

    def boom(path, **kw):
        raise RuntimeError("model exploded")

    monkeypatch.setattr("kord.queue.transcribe_bass", boom)
    db.enqueue_tab_job(conn, "t1")

    assert run_one_tab_job(conn, TabStore(tmp_path / "tabs"), stem_store) == "failed"
    assert "model exploded" in db.tab_job_for(conn, "t1")["error"]
