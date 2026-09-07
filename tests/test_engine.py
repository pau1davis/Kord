"""The worker and the API must agree on the engine version.

If they disagreed, the worker would write analyses under one key and the API
would look them up under another — every cache read would miss in silence and
songs would re-analyze on every view.
"""
import pytest

from kord.analysis.btc import WEIGHTS_FILENAME
from kord.config import Settings
from kord.engine import BTC_VERSION, CHROMA_VERSION, build_recognizer, resolve_engine_version


def settings_for(tmp_path, engine_version="chroma-1") -> Settings:
    models = tmp_path / "models"
    models.mkdir(exist_ok=True)
    audio = tmp_path / "audio"
    audio.mkdir(exist_ok=True)
    stems = tmp_path / "stems"
    stems.mkdir(exist_ok=True)
    tabs = tmp_path / "tabs"
    tabs.mkdir(exist_ok=True)
    return Settings("cid", "http://127.0.0.1:8000/api/auth/callback",
                    tmp_path / "k.db", tmp_path, engine_version, models,
                    "http://127.0.0.1:5173", audio, 2 * 1024 ** 3, stems, tabs,
                    None)


def test_falls_back_to_chroma_without_weights(tmp_path, monkeypatch):
    monkeypatch.delenv("KORD_ENGINE_VERSION", raising=False)
    assert resolve_engine_version(settings_for(tmp_path)) == CHROMA_VERSION


def test_prefers_btc_when_weights_are_present(tmp_path, monkeypatch):
    monkeypatch.delenv("KORD_ENGINE_VERSION", raising=False)
    settings = settings_for(tmp_path)
    (settings.model_dir / WEIGHTS_FILENAME).write_bytes(b"fake weights")
    assert resolve_engine_version(settings) == BTC_VERSION


def test_explicit_env_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("KORD_ENGINE_VERSION", "chroma-1")
    settings = settings_for(tmp_path, engine_version="chroma-1")
    (settings.model_dir / WEIGHTS_FILENAME).write_bytes(b"fake weights")
    assert resolve_engine_version(settings) == CHROMA_VERSION


def test_recognizer_and_version_always_agree(tmp_path, monkeypatch):
    monkeypatch.delenv("KORD_ENGINE_VERSION", raising=False)
    recognizer, version = build_recognizer(settings_for(tmp_path))
    assert recognizer.engine_version == version
    assert version == resolve_engine_version(settings_for(tmp_path))


def test_pinning_btc_without_weights_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setenv("KORD_ENGINE_VERSION", BTC_VERSION)
    settings = settings_for(tmp_path, engine_version=BTC_VERSION)
    with pytest.raises(FileNotFoundError, match="weights are missing"):
        build_recognizer(settings)
