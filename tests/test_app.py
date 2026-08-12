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

    async def get_track(self, track_id, token):
        return {"id": track_id, "title": "Creep", "artist": "Radiohead",
                "album": "Pablo Honey", "duration_ms": 238640, "image": None}


def settings_for(tmp_path):
    models = tmp_path / "models"
    models.mkdir(exist_ok=True)
    return Settings("cid", "http://127.0.0.1:8000/api/auth/callback",
                    tmp_path / "x.db", tmp_path, "chroma-1", models,
                    "http://127.0.0.1:5173")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    conn = db.connect(":memory:")
    db.init_schema(conn)
    app = create_app(settings_for(tmp_path), FakeSpotify(), conn)
    app.state.access_token = "tok"       # pretend we are logged in
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
