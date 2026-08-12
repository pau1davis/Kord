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
    model_dir: Path
    ui_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(os.environ.get("KORD_HOME", Path.home() / ".kord"))
        root.mkdir(parents=True, exist_ok=True)
        scratch = root / "scratch"
        scratch.mkdir(exist_ok=True)
        # Model weights live outside the repository so a 12 MB binary never
        # enters git history.
        models = root / "models"
        models.mkdir(exist_ok=True)
        return cls(
            spotify_client_id=os.environ.get("SPOTIFY_CLIENT_ID", ""),
            # Spotify rejects `localhost` in a redirect URI as insecure: hostname
            # resolution can be hijacked, so it requires the explicit loopback IP.
            # HTTP is permitted for loopback addresses.
            redirect_uri=os.environ.get(
                "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/callback"),
            db_path=root / "kord.db",
            scratch_dir=scratch,
            engine_version=os.environ.get("KORD_ENGINE_VERSION", "chroma-1"),
            model_dir=models,
            # Where to send the browser after authorising. The UI runs on its own
            # port, so returning to the API's root would land on a JSON 404.
            ui_url=os.environ.get("KORD_UI_URL", "http://127.0.0.1:5173"),
        )
