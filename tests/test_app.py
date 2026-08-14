import pytest
from fastapi.testclient import TestClient

from kord import db
from kord.app import create_app
from kord.config import Settings
from kord.models import Analysis, BeatGrid, ChordSegment, KeyEstimate


class FakeSpotify:
    async def search_tracks(self, query, token, limit=20):
        return [{"id": "t1", "title": "Creep", "artist": "Radiohead",
                 "album": "Pablo Honey", "duration_ms": 238640, "image": None}]

    async def recently_played(self, token, limit=20):
        one = {"id": "t1", "title": "Creep", "artist": "Radiohead",
               "album": "Pablo Honey", "duration_ms": 238640, "image": None}
        return [one]

    async def top_tracks(self, token, limit=50, time_range="medium_term"):
        return [{"id": "t1", "title": "Creep", "artist": "Radiohead",
                 "album": "Pablo Honey", "duration_ms": 238640, "image": None}]

    async def get_track(self, track_id, token):
        return {"id": track_id, "title": "Creep", "artist": "Radiohead",
                "album": "Pablo Honey", "duration_ms": 238640, "image": None}


def settings_for(tmp_path):
    models = tmp_path / "models"
    models.mkdir(exist_ok=True)
    audio = tmp_path / "audio"
    audio.mkdir(exist_ok=True)
    stems = tmp_path / "stems"
    stems.mkdir(exist_ok=True)
    return Settings("cid", "http://127.0.0.1:8000/api/auth/callback",
                    tmp_path / "x.db", tmp_path, "chroma-1", models,
                    "http://127.0.0.1:5173", audio, 2 * 1024 ** 3, stems)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    # A real signed-in session, not just a cached token: expiry is read from
    # the stored session on every call, so there has to be one.
    db.save_session(conn, "tok", "rt", 3600)
    app = create_app(settings_for(tmp_path), FakeSpotify(), conn)
    return TestClient(app), conn


def save_fixture_analysis(conn, segments, key=None, flags=None):
    db.upsert_track(conn, "t1", "Radiohead", "Creep", "Pablo Honey", 238640)
    db.save_analysis(conn, Analysis(
        spotify_id="t1", engine_version="chroma-1",
        key=key or KeyEstimate(0, "major", 0.85, True), tempo=92.0,
        beat_grid=BeatGrid([0.0, 0.65], 92.0), chord_segments=segments,
        source_url="u", source_duration_ms=238000, time_scale=1.0,
        sync_offset_ms=0, flags=flags or [], chord_confidence_mean=0.85))


def test_health(client):
    c, _ = client
    assert c.get("/api/health").json()["status"] == "ok"


def test_auth_status_reports_logged_out_without_token(tmp_path):
    conn = db.connect(":memory:")
    db.init_schema(conn)
    c = TestClient(create_app(settings_for(tmp_path), FakeSpotify(), conn))
    assert c.get("/api/auth/status").json()["authenticated"] is False


def test_protected_routes_401_without_a_token(tmp_path):
    conn = db.connect(":memory:")
    db.init_schema(conn)
    c = TestClient(create_app(settings_for(tmp_path), FakeSpotify(), conn))
    assert c.get("/api/search", params={"q": "x"}).status_code == 401


def test_search_returns_tracks(client):
    c, _ = client
    assert c.get("/api/search", params={"q": "creep"}).json()[0]["artist"] == "Radiohead"


def test_track_without_analysis_reports_pending_and_enqueues(client):
    c, conn = client
    body = c.get("/api/track/t1").json()
    assert body["status"] == "pending"
    assert body["track"]["title"] == "Creep"
    assert conn.execute("SELECT COUNT(*) c FROM job").fetchone()["c"] == 1


def test_track_with_analysis_returns_chart_theory_and_palette(client):
    c, conn = client
    save_fixture_analysis(conn, [
        ChordSegment(0.0, 4.0, 0, "major", 0.9),
        ChordSegment(4.0, 8.0, 9, "minor", 0.8)])
    body = c.get("/api/track/t1").json()
    assert body["status"] == "done"
    assert body["theory"]["key"] == "C major"
    assert body["chart"][0]["roman"] == "I"
    assert body["chart"][1]["roman"] == "vi"
    assert body["chart"][0]["label"] == "C"
    assert body["chart"][1]["label"] == "Am"
    assert body["palette"][0]["hue"] in (40, 220)
    assert body["theory"]["scale"]["notes"][0] == "C"


def test_low_confidence_segments_are_marked_uncertain(client):
    c, conn = client
    save_fixture_analysis(
        conn, [ChordSegment(0.0, 4.0, 0, "major", 0.20)],
        key=KeyEstimate(0, "major", 0.4, False))
    body = c.get("/api/track/t1").json()
    assert body["chart"][0]["uncertain"] is True
    assert body["theory"]["key_uncertain"] is True


def test_confident_output_is_not_marked_uncertain(client):
    c, conn = client
    save_fixture_analysis(conn, [ChordSegment(0.0, 4.0, 0, "major", 0.95)])
    body = c.get("/api/track/t1").json()
    assert body["chart"][0]["uncertain"] is False
    assert body["theory"]["key_uncertain"] is False


def test_no_chord_segments_are_excluded_from_the_chart(client):
    c, conn = client
    save_fixture_analysis(conn, [
        ChordSegment(0.0, 2.0, -1, "none", 0.0),
        ChordSegment(2.0, 4.0, 0, "major", 0.9)])
    body = c.get("/api/track/t1").json()
    assert [entry["label"] for entry in body["chart"]] == ["C"]


def test_speed_adjusted_flag_is_surfaced(client):
    c, conn = client
    save_fixture_analysis(
        conn, [ChordSegment(0.0, 4.0, 0, "major", 0.9)], flags=["speed_adjusted"])
    assert "speed_adjusted" in c.get("/api/track/t1").json()["flags"]


def test_analyze_endpoint_is_idempotent(client):
    c, conn = client
    c.post("/api/track/t1/analyze")
    c.post("/api/track/t1/analyze")
    assert conn.execute("SELECT COUNT(*) c FROM job").fetchone()["c"] == 1


def test_failed_job_surfaces_its_reason(client):
    c, conn = client
    db.upsert_track(conn, "t1", "Radiohead", "Creep", "Pablo Honey", 238640)
    job_id = db.enqueue_job(conn, "t1")
    db.finish_job(conn, job_id, "unavailable", "no candidate matched duration")
    body = c.get("/api/track/t1").json()
    assert body["status"] == "unavailable"
    assert "duration" in body["error"]


def test_build_app_is_a_zero_argument_uvicorn_factory(tmp_path, monkeypatch):
    """The documented run command depends on this signature.

    create_app takes injected dependencies so tests can pass fakes, which makes
    it unusable as a uvicorn --factory. build_app is the production entrypoint.
    """
    import inspect

    from kord.app import build_app

    assert inspect.signature(build_app).parameters == {}

    monkeypatch.setenv("KORD_HOME", str(tmp_path))
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    app = build_app()
    client = TestClient(app)
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/auth/status").json()["authenticated"] is False


class TokenSpotify(FakeSpotify):
    async def exchange_code(self, code, verifier, redirect_uri):
        return {"access_token": "at", "refresh_token": "rt"}


def test_auth_callback_returns_to_the_ui_not_the_api_root(tmp_path):
    """Landing on the API's own root after authorising shows a JSON 404.

    The UI runs on a different port, so the callback must send the browser there.
    """
    conn = db.connect(":memory:")
    db.init_schema(conn)
    app = create_app(settings_for(tmp_path), TokenSpotify(), conn)
    client = TestClient(app)
    client.get("/api/auth/login")                      # establishes the verifier
    response = client.get(
        "/api/auth/callback", params={"code": "abc"}, follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "http://127.0.0.1:5173"


def test_default_redirect_uri_uses_the_loopback_ip_not_localhost(monkeypatch):
    """Spotify rejects `localhost` in a redirect URI as insecure.

    It requires the explicit loopback IP, since hostname resolution can be hijacked.
    """
    monkeypatch.delenv("SPOTIFY_REDIRECT_URI", raising=False)
    monkeypatch.setenv("KORD_HOME", "/tmp/kord-uri-test")
    settings = Settings.from_env()
    assert "localhost" not in settings.redirect_uri
    assert settings.redirect_uri.startswith("http://127.0.0.1:8000")
    assert "localhost" not in settings.ui_url


def test_callback_without_a_code_explains_itself(tmp_path):
    """A human reads this page in a browser; a raw 422 tells them nothing."""
    conn = db.connect(":memory:")
    db.init_schema(conn)
    client = TestClient(create_app(settings_for(tmp_path), TokenSpotify(), conn))
    response = client.get("/api/auth/callback", follow_redirects=False)
    assert response.status_code == 400
    assert "text/html" in response.headers["content-type"]
    assert "/api/auth/login" in response.text


def test_callback_surfaces_spotifys_own_error(tmp_path):
    conn = db.connect(":memory:")
    db.init_schema(conn)
    client = TestClient(create_app(settings_for(tmp_path), TokenSpotify(), conn))
    response = client.get(
        "/api/auth/callback", params={"error": "access_denied"},
        follow_redirects=False)
    assert response.status_code == 400
    assert "access_denied" in response.text


def test_callback_without_a_verifier_explains_the_restart(tmp_path):
    """Server restarts lose the in-memory PKCE verifier."""
    conn = db.connect(":memory:")
    db.init_schema(conn)
    client = TestClient(create_app(settings_for(tmp_path), TokenSpotify(), conn))
    response = client.get(
        "/api/auth/callback", params={"code": "abc"}, follow_redirects=False)
    assert response.status_code == 400
    assert "/api/auth/login" in response.text


def test_audio_endpoint_serves_a_retained_file(tmp_path, monkeypatch):
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)

    settings = settings_for(tmp_path)
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    (settings.audio_dir / "t1.webm").write_bytes(b"0123456789")
    db.set_audio_ext(conn, "t1", ".webm")

    client = TestClient(create_app(settings, FakeSpotify(), conn))
    response = client.get("/api/track/t1/audio")
    assert response.status_code == 200
    assert response.content == b"0123456789"


def test_audio_endpoint_honours_range_requests(tmp_path, monkeypatch):
    """Seeking and looping depend on 206. Without it they break silently."""
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)

    settings = settings_for(tmp_path)
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    (settings.audio_dir / "t1.webm").write_bytes(b"0123456789")
    db.set_audio_ext(conn, "t1", ".webm")

    client = TestClient(create_app(settings, FakeSpotify(), conn))
    response = client.get("/api/track/t1/audio", headers={"Range": "bytes=2-5"})
    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"


def test_audio_endpoint_404s_when_evicted(tmp_path, monkeypatch):
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)
    client = TestClient(create_app(settings_for(tmp_path), FakeSpotify(), conn))
    assert client.get("/api/track/t1/audio").status_code == 404


def test_playing_records_the_play_for_eviction_ordering(tmp_path, monkeypatch):
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)

    settings = settings_for(tmp_path)
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    (settings.audio_dir / "t1.webm").write_bytes(b"x")
    db.set_audio_ext(conn, "t1", ".webm")

    client = TestClient(create_app(settings, FakeSpotify(), conn))
    client.get("/api/track/t1/audio")
    row = conn.execute("SELECT last_played_at FROM track WHERE spotify_id='t1'").fetchone()
    assert row["last_played_at"] is not None


def test_track_payload_includes_sections(client):
    c, conn = client
    from kord.models import Section
    db.upsert_track(conn, "t1", "Radiohead", "Creep", "Pablo Honey", 238640)
    db.save_analysis(conn, Analysis(
        spotify_id="t1", engine_version="chroma-1",
        key=KeyEstimate(0, "major", 0.85, True), tempo=92.0,
        beat_grid=BeatGrid([0.0, 0.65], 92.0),
        chord_segments=[ChordSegment(0.0, 4.0, 0, "major", 0.9)],
        source_url="u", source_duration_ms=238000, time_scale=1.0,
        sync_offset_ms=511, flags=[], chord_confidence_mean=0.85,
        sections=[Section(0.0, 30.0, "A"), Section(30.0, 60.0, "B")]))
    body = c.get("/api/track/t1").json()
    assert body["sections"] == [
        {"start_s": 0.0, "end_s": 30.0, "label": "A"},
        {"start_s": 30.0, "end_s": 60.0, "label": "B"},
    ]
    assert body["sync_offset_ms"] == 511


def test_track_payload_reports_whether_audio_is_available(client):
    c, conn = client
    save_fixture_analysis(conn, [ChordSegment(0.0, 4.0, 0, "major", 0.9)])
    assert c.get("/api/track/t1").json()["has_audio"] is False


def test_track_payload_includes_the_beat_grid(client):
    """BeatStrip needs these; they were stored in Phase 1 but never sent."""
    c, conn = client
    save_fixture_analysis(conn, [ChordSegment(0.0, 4.0, 0, "major", 0.9)])
    assert c.get("/api/track/t1").json()["beats"] == [0.0, 0.65]


class RefreshingSpotify(FakeSpotify):
    """Records which access token each call actually used."""

    def __init__(self):
        self.refreshed = 0
        self.tokens_seen = []

    async def refresh(self, refresh_token):
        self.refreshed += 1
        return {"access_token": "fresh", "expires_in": 3600}

    async def search_tracks(self, query, token, limit=20):
        self.tokens_seen.append(token)
        return await super().search_tracks(query, token, limit)


def test_expired_cached_token_is_refreshed_rather_than_reused(tmp_path, monkeypatch):
    """The in-memory token outlives its expiry.

    It is cached at startup while still valid, so every later call short
    circuits on it and Spotify 401s until the process restarts.
    """
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.save_session(conn, "stale", "rt", -10)
    spotify = RefreshingSpotify()
    app = create_app(settings_for(tmp_path), spotify, conn)
    app.state.access_token = "stale"  # cached back when it was still valid
    client = TestClient(app)

    assert client.get("/api/search?q=creep").status_code == 200
    assert spotify.refreshed == 1
    assert spotify.tokens_seen == ["fresh"]


def _session_client(tmp_path, monkeypatch, access, refresh, expires_in):
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.save_session(conn, access, refresh, expires_in)
    app = create_app(settings_for(tmp_path), FakeSpotify(), conn)
    app.state.access_token = access  # cached back when it was still valid
    return TestClient(app)


def test_auth_status_is_connected_when_only_a_refresh_is_needed(tmp_path, monkeypatch):
    """A refreshable session is usable, so the UI must not demand a reconnect."""
    client = _session_client(tmp_path, monkeypatch, "stale", "rt", -10)
    assert client.get("/api/auth/status").json()["authenticated"] is True


def test_auth_status_is_disconnected_when_the_token_died_unrefreshably(
        tmp_path, monkeypatch):
    """The failure that stranded the UI: status said connected, every search 401d."""
    client = _session_client(tmp_path, monkeypatch, "stale", None, -10)
    assert client.get("/api/auth/status").json()["authenticated"] is False


def test_audio_endpoint_pins_m4a_to_audio_mp4(tmp_path, monkeypatch):
    """mimetypes guesses audio/mp4a-latm for .m4a, which browsers refuse."""
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)

    settings = settings_for(tmp_path)
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    (settings.audio_dir / "t1.m4a").write_bytes(b"0123456789")
    db.set_audio_ext(conn, "t1", ".m4a")

    client = TestClient(create_app(settings, FakeSpotify(), conn))
    response = client.get("/api/track/t1/audio")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mp4"


def test_audio_endpoint_serves_webm_as_audio_not_video(tmp_path, monkeypatch):
    """The file is audio-only; video/webm is what mimetypes would have said."""
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)

    settings = settings_for(tmp_path)
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    (settings.audio_dir / "t1.webm").write_bytes(b"0123456789")
    db.set_audio_ext(conn, "t1", ".webm")

    client = TestClient(create_app(settings, FakeSpotify(), conn))
    response = client.get("/api/track/t1/audio")
    assert response.headers["content-type"] == "audio/webm"


def test_requesting_stems_enqueues_a_job(client):
    c, conn = client
    body = c.post("/api/track/t1/stems").json()
    assert body["status"] == "pending"
    assert db.stem_job_for(conn, "t1")["state"] == "pending"


def test_requesting_stems_twice_is_idempotent(client):
    c, _ = client
    first = c.post("/api/track/t1/stems").json()["job_id"]
    assert c.post("/api/track/t1/stems").json()["job_id"] == first


def test_stem_status_lists_available_stems(tmp_path, monkeypatch):
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)

    settings = settings_for(tmp_path)
    (settings.stems_dir / "t1").mkdir(parents=True, exist_ok=True)
    (settings.stems_dir / "t1" / "guitar.m4a").write_bytes(b"x")
    db.enqueue_stem_job(conn, "t1")
    db.finish_stem_job(conn, db.stem_job_for(conn, "t1")["id"], "done")

    c = TestClient(create_app(settings, FakeSpotify(), conn))
    body = c.get("/api/track/t1/stems").json()
    assert body["status"] == "done"
    assert "guitar" in body["available"]


def test_stem_status_is_none_before_anything_is_requested(tmp_path, monkeypatch):
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)
    c = TestClient(create_app(settings_for(tmp_path), FakeSpotify(), conn))
    body = c.get("/api/track/t1/stems").json()
    assert body["status"] == "none"
    assert body["available"] == []


def test_stem_file_is_served_as_audio_mp4(tmp_path, monkeypatch):
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)

    settings = settings_for(tmp_path)
    (settings.stems_dir / "t1").mkdir(parents=True, exist_ok=True)
    (settings.stems_dir / "t1" / "guitar.m4a").write_bytes(b"0123456789")

    c = TestClient(create_app(settings, FakeSpotify(), conn))
    response = c.get("/api/track/t1/stems/guitar")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mp4"
    assert response.content == b"0123456789"


def test_unknown_stem_name_404s(tmp_path, monkeypatch):
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    db.upsert_track(conn, "t1", "A", "T", "Al", 1000)
    c = TestClient(create_app(settings_for(tmp_path), FakeSpotify(), conn))
    assert c.get("/api/track/t1/stems/trombone").status_code == 404


def test_me_top_returns_the_users_tracks(client):
    c, _ = client
    body = c.get("/api/me/top").json()
    assert body[0]["artist"] == "Radiohead"


def test_taste_reports_progress_before_anything_is_analysed(client):
    c, _ = client
    body = c.get("/api/me/taste").json()
    assert body["analyzed"] == 0
    assert body["total"] == 1
    assert body["palette"] == []


def test_analysing_top_tracks_enqueues_each_one(client):
    c, conn = client
    body = c.post("/api/me/top/analyze").json()
    assert body["queued"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM job").fetchone()["c"] == 1


def test_analysing_top_tracks_twice_does_not_double_queue(client):
    c, conn = client
    c.post("/api/me/top/analyze")
    c.post("/api/me/top/analyze")
    assert conn.execute("SELECT COUNT(*) c FROM job").fetchone()["c"] == 1


def test_recently_played_is_deduplicated(client):
    c, _ = client
    body = c.get("/api/me/recent").json()
    assert [t["id"] for t in body] == ["t1"], "the same song played twice is one row"


def test_library_reports_local_state_without_calling_spotify(client):
    c, conn = client
    save_fixture_analysis(conn, [ChordSegment(0.0, 4.0, 0, "major", 0.9)])
    conn.execute("UPDATE track SET last_played_at='2026-08-14' WHERE spotify_id='t1'")
    conn.commit()
    body = c.get("/api/me/library").json()
    assert body["analyzed"] == 1
    assert body["resume"]["title"] == "Creep"
    assert body["resume"]["key"].startswith("C")
    assert body["keys"][0]["count"] == 1


def test_library_without_history_has_nothing_to_resume(client):
    c, _ = client
    body = c.get("/api/me/library").json()
    assert body["resume"] is None
    assert body["analyzed"] == 0
