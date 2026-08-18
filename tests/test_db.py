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


def test_stem_jobs_are_claimed_once_each():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)
    job_id = db.enqueue_stem_job(conn, "t1")

    first = db.claim_stem_job(conn)
    assert first["id"] == job_id
    assert db.claim_stem_job(conn) is None, "a claimed job must not be reclaimed"

    db.finish_stem_job(conn, job_id, "done")
    assert db.stem_job_for(conn, "t1")["state"] == "done"


def test_enqueueing_stems_twice_reuses_the_pending_job():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)
    assert db.enqueue_stem_job(conn, "t1") == db.enqueue_stem_job(conn, "t1")


def test_a_failed_stem_job_records_its_reason():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)
    job_id = db.enqueue_stem_job(conn, "t1")
    db.claim_stem_job(conn)
    db.finish_stem_job(conn, job_id, "failed", "model exploded")
    row = db.stem_job_for(conn, "t1")
    assert row["state"] == "failed"
    assert "exploded" in row["error"]


def test_recently_opened_is_most_recent_first():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    for tid in ("t1", "t2", "t3"):
        db.upsert_track(conn, tid, "A", tid, "Al", 1000)
    conn.execute("UPDATE track SET last_played_at='2026-01-01' WHERE spotify_id='t1'")
    conn.execute("UPDATE track SET last_played_at='2026-03-01' WHERE spotify_id='t2'")
    conn.commit()
    rows = db.recently_opened(conn)
    assert [r["spotify_id"] for r in rows] == ["t2", "t1"], "t3 was never played"


def test_counts_tracks_with_retained_audio():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)
    db.upsert_track(conn, "t2", "A", "T", "Al", 1000)
    db.set_audio_ext(conn, "t1", ".m4a")
    assert db.count_tracks_with_audio(conn) == 1


def test_stem_progress_is_recorded_and_read_back():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)
    job_id = db.enqueue_stem_job(conn, "t1")
    assert db.stem_job_for(conn, "t1")["progress"] == 0
    db.set_stem_progress(conn, job_id, 0.42)
    assert db.stem_job_for(conn, "t1")["progress"] == pytest.approx(0.42)


def test_finishing_a_stem_job_completes_its_progress():
    """A done job showing 87% would read as still working."""
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)
    job_id = db.enqueue_stem_job(conn, "t1")
    db.set_stem_progress(conn, job_id, 0.87)
    db.finish_stem_job(conn, job_id, "done")
    assert db.stem_job_for(conn, "t1")["progress"] == 1.0


def _analysis(spotify_id, engine_version, tempo=92.0):
    from kord.models import Analysis, BeatGrid, KeyEstimate
    return Analysis(
        spotify_id=spotify_id, engine_version=engine_version,
        key=KeyEstimate(0, "major", 0.85, True), tempo=tempo,
        beat_grid=BeatGrid([0.0, 0.65], tempo), chord_segments=[],
        source_url="u", source_duration_ms=1000, time_scale=1.0,
        sync_offset_ms=0)


def test_best_analysis_prefers_the_current_engine(tmp_path):
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.save_analysis(conn, _analysis("t1", "btc-4", tempo=90.0))
    db.save_analysis(conn, _analysis("t1", "btc-5", tempo=120.0))
    found, current = db.best_analysis(conn, "t1", "btc-5")
    assert found.tempo == 120.0
    assert current is True


def test_best_analysis_falls_back_to_an_older_engine(tmp_path):
    """An engine bump must not blank a library.

    Bumping to btc-5 made every btc-4 analysis unreachable, so 25 songs that
    worked an hour earlier read as unavailable — and the re-analysis that would
    have fixed them was being refused by YouTube with 403s.
    """
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.save_analysis(conn, _analysis("t1", "btc-4", tempo=90.0))
    found, current = db.best_analysis(conn, "t1", "btc-5")
    assert found.tempo == 90.0
    assert current is False


def test_best_analysis_picks_the_newest_of_several_old_engines(tmp_path):
    conn = db.connect(":memory:")
    db.init_schema(conn)
    for version, tempo in (("btc-1", 60.0), ("btc-3", 80.0), ("btc-4", 90.0)):
        db.save_analysis(conn, _analysis("t1", version, tempo=tempo))
    found, current = db.best_analysis(conn, "t1", "btc-5")
    assert found.tempo == 90.0, "should serve the most recently analysed"
    assert current is False


def test_best_analysis_reports_nothing_when_there_is_nothing(tmp_path):
    conn = db.connect(":memory:")
    db.init_schema(conn)
    assert db.best_analysis(conn, "t1", "btc-5") == (None, False)


def test_a_tempo_correction_is_remembered(tmp_path):
    conn = db.connect(":memory:")
    db.init_schema(conn)
    assert db.get_tempo_factor(conn, "t1") == 1.0
    db.set_tempo_factor(conn, "t1", 2.0)
    assert db.get_tempo_factor(conn, "t1") == 2.0


def test_setting_it_back_to_one_forgets_it(tmp_path):
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.set_tempo_factor(conn, "t1", 0.5)
    db.set_tempo_factor(conn, "t1", 1.0)
    assert db.get_tempo_factor(conn, "t1") == 1.0
    assert conn.execute("SELECT COUNT(*) c FROM tempo_override").fetchone()["c"] == 0


def test_a_correction_outlives_re_analysis(tmp_path):
    """It is the player's judgement about the song, not the analyser's output,
    so an engine bump must not throw it away."""
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.save_analysis(conn, _analysis("t1", "btc-4"))
    db.set_tempo_factor(conn, "t1", 2.0)
    db.save_analysis(conn, _analysis("t1", "btc-5"))
    assert db.get_tempo_factor(conn, "t1") == 2.0


def test_reclaiming_returns_wedged_jobs_to_the_queue(tmp_path):
    """A worker killed mid-job leaves it 'running' forever, and nothing else
    ever picks it up — the song shows "pending" for good. This has stranded a
    job twice: once on an Aug 12 crash, once on the shutdown of Aug 17.
    """
    conn = db.connect(":memory:")
    db.init_schema(conn)
    for table, enqueue in (("job", db.enqueue_job),
                           ("stem_job", db.enqueue_stem_job),
                           ("tab_job", db.enqueue_tab_job)):
        enqueue(conn, "t1")
        conn.execute(f"UPDATE {table} SET state='running'")
    conn.commit()

    assert db.reclaim_running_jobs(conn) == 3
    for table in ("job", "stem_job", "tab_job"):
        states = [r[0] for r in conn.execute(f"SELECT state FROM {table}")]
        assert states == ["pending"], table


def test_reclaiming_leaves_finished_work_alone(tmp_path):
    conn = db.connect(":memory:")
    db.init_schema(conn)
    job_id = db.enqueue_job(conn, "t1")
    db.finish_job(conn, job_id, "done")
    assert db.reclaim_running_jobs(conn) == 0
    assert conn.execute("SELECT state FROM job").fetchone()[0] == "done"


def test_reclaiming_an_empty_queue_is_not_a_crash(tmp_path):
    conn = db.connect(":memory:")
    db.init_schema(conn)
    assert db.reclaim_running_jobs(conn) == 0
