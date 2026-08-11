from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    spotify_client_id: str
    redirect_uri: str
    db_path: Path
    scratch_dir: Path
    engine_version: str

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(os.environ.get("KORD_HOME", Path.home() / ".kord"))
        root.mkdir(parents=True, exist_ok=True)
        scratch = root / "scratch"
        scratch.mkdir(exist_ok=True)
        return cls(
            spotify_client_id=os.environ.get("SPOTIFY_CLIENT_ID", ""),
            redirect_uri=os.environ.get(
                "SPOTIFY_REDIRECT_URI", "http://localhost:8000/api/auth/callback"),
            db_path=root / "kord.db",
            scratch_dir=scratch,
            engine_version=os.environ.get("KORD_ENGINE_VERSION", "chroma-1"),
        )
