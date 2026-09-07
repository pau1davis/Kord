import shutil
from pathlib import Path

import pytest

from kord import db
from kord.audio.store import AudioStore


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_schema(c)
    return c


def make_source(tmp_path, name="a.webm", size=1024):
    p = tmp_path / name
    p.write_bytes(b"x" * size)
    return p


def test_retain_copies_and_locates(tmp_path, conn):
    store = AudioStore(tmp_path / "audio", cap_bytes=10_000)
    kept = store.retain("t1", make_source(tmp_path))
    assert kept.exists()
    assert store.path_for("t1") == kept


def test_path_for_returns_none_when_absent(tmp_path):
    assert AudioStore(tmp_path / "audio", cap_bytes=10_000).path_for("nope") is None


def test_retain_preserves_the_extension(tmp_path, conn):
    store = AudioStore(tmp_path / "audio", cap_bytes=10_000)
    kept = store.retain("t1", make_source(tmp_path, "a.m4a"))
    assert kept.suffix == ".m4a"


def test_retain_replaces_an_existing_file(tmp_path, conn):
    store = AudioStore(tmp_path / "audio", cap_bytes=10_000)
    store.retain("t1", make_source(tmp_path, "a.webm", 100))
    store.retain("t1", make_source(tmp_path, "b.webm", 500))
    assert store.path_for("t1").stat().st_size == 500
    assert store.total_bytes() == 500


def test_total_bytes_sums_the_store(tmp_path, conn):
    store = AudioStore(tmp_path / "audio", cap_bytes=10_000)
    store.retain("t1", make_source(tmp_path, "a.webm", 300))
    store.retain("t2", make_source(tmp_path, "b.webm", 200))
    assert store.total_bytes() == 500


def test_eviction_removes_least_recently_played_first(tmp_path, conn):
    store = AudioStore(tmp_path / "audio", cap_bytes=1000)
    for tid, size in (("old", 400), ("mid", 400)):
        db.upsert_track(conn, tid, "A", tid, "Al", 1000)
        store.retain(tid, make_source(tmp_path, f"{tid}.webm", size))
        db.set_audio_ext(conn, tid, ".webm")
    db.touch_played(conn, "old")
    db.touch_played(conn, "mid")      # mid is newer, so old goes first

    evicted = store.evict_to_fit(conn, incoming_bytes=400)
    assert evicted == ["old"]
    assert store.path_for("old") is None
    assert store.path_for("mid") is not None


def test_eviction_stops_once_it_fits(tmp_path, conn):
    store = AudioStore(tmp_path / "audio", cap_bytes=10_000)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)
    store.retain("t1", make_source(tmp_path, "a.webm", 100))
    db.set_audio_ext(conn, "t1", ".webm")
    assert store.evict_to_fit(conn, incoming_bytes=100) == []
    assert store.path_for("t1") is not None


def test_retain_failure_leaves_no_truncated_file(tmp_path, conn, monkeypatch):
    """A failure partway through must never leave a stub at the final name.

    Simulates a disk-full mid-copy: the fake copy2 partially writes its
    destination and then raises, same as a real `shutil.copy2` would. Because
    `retain` now copies to a hidden temp name and `os.replace`s it in, the
    partial write should land on the temp file only — the previous good copy
    at the real name must survive untouched, and no stray temp file remains.
    """
    store = AudioStore(tmp_path / "audio", cap_bytes=10_000)
    good = store.retain("t1", make_source(tmp_path, "a.webm", 100))

    def broken_copy2(src, dst):
        Path(dst).write_bytes(b"x" * 10)
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copy2", broken_copy2)

    with pytest.raises(OSError):
        store.retain("t1", make_source(tmp_path, "b.webm", 500))

    assert store.path_for("t1") == good, "previous good copy must still be there"
    assert good.stat().st_size == 100, "must not have been overwritten with a stub"
    assert list((tmp_path / "audio").iterdir()) == [good], "no stray temp file left behind"


def test_eviction_keeps_the_analysis(tmp_path, conn):
    """An evicted song is not broken - only its audio is gone."""
    from kord.models import Analysis, BeatGrid, ChordSegment, KeyEstimate

    store = AudioStore(tmp_path / "audio", cap_bytes=100)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)
    db.save_analysis(conn, Analysis(
        spotify_id="t1", engine_version="btc-3", key=KeyEstimate(0, "major", 0.8, True),
        tempo=120.0, beat_grid=BeatGrid([0.0], 120.0),
        chord_segments=[ChordSegment(0.0, 1.0, 0, "major", 0.9)],
        source_url="u", source_duration_ms=1000, time_scale=1.0, sync_offset_ms=0))
    store.retain("t1", make_source(tmp_path, "a.webm", 100))
    db.set_audio_ext(conn, "t1", ".webm")

    store.evict_to_fit(conn, incoming_bytes=100)
    assert store.path_for("t1") is None
    assert db.get_analysis(conn, "t1", "btc-3") is not None


def test_an_imported_file_is_never_evicted(tmp_path, conn):
    """Downloaded audio can be fetched again; an imported file cannot.

    Evicting it deletes the only copy Kord has, and the track becomes
    unanalysable with nothing to rebuild it from. A cap should only ever
    reclaim what it can replace.
    """
    store = AudioStore(tmp_path / "audio", cap_bytes=1000)
    for tid, size in (("file:abc123", 400), ("downloaded", 400)):
        db.upsert_track(conn, tid, "A", tid, "Al", 1000)
        store.retain(tid, make_source(tmp_path, "x.webm", size))
        db.set_audio_ext(conn, tid, ".webm")
    # The import is never played, so the ordering would otherwise pick it
    # first — never-played sorts as most evictable.
    db.touch_played(conn, "downloaded")

    evicted = store.evict_to_fit(conn, incoming_bytes=400)
    assert evicted == ["downloaded"]
    assert store.path_for("file:abc123") is not None


def test_the_cap_may_be_exceeded_rather_than_lose_an_import(tmp_path, conn):
    """If imports are all that is left, the store goes over its cap. That is
    the deliberate trade: a cap is a disk-space convenience, and losing a
    file the user gave us is not recoverable."""
    store = AudioStore(tmp_path / "audio", cap_bytes=500)
    for tid in ("file:one", "file:two"):
        db.upsert_track(conn, tid, "A", tid, "Al", 1000)
        store.retain(tid, make_source(tmp_path, "x.webm", 400))
        db.set_audio_ext(conn, tid, ".webm")

    assert store.evict_to_fit(conn, incoming_bytes=400) == []
    assert store.path_for("file:one") is not None
    assert store.path_for("file:two") is not None
