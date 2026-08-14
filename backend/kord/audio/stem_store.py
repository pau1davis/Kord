from __future__ import annotations

import shutil
from pathlib import Path

from kord.audio.stems import STEM_NAMES


class StemStore:
    """Separated stems on disk, one directory per song."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def dir_for(self, spotify_id: str) -> Path:
        return self.root / spotify_id

    def path_for(self, spotify_id: str, stem: str) -> Path | None:
        # `stem` arrives from a URL path segment, so it is checked against the
        # known names rather than sanitised — a whitelist cannot be talked out
        # of by a traversal sequence.
        if stem not in STEM_NAMES:
            return None
        path = self.dir_for(spotify_id) / f"{stem}.m4a"
        return path if path.exists() else None

    def has_stems(self, spotify_id: str) -> bool:
        directory = self.dir_for(spotify_id)
        return directory.is_dir() and any(directory.glob("*.m4a"))

    def total_bytes(self) -> int:
        return sum(
            p.stat().st_size for p in self.root.rglob("*.m4a") if p.is_file())

    def remove(self, spotify_id: str) -> None:
        shutil.rmtree(self.dir_for(spotify_id), ignore_errors=True)
