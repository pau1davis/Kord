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

    def present(self, spotify_id: str, names) -> list[str]:
        """The parts actually in this song, cached beside the stems.

        Measuring six whole songs' worth of audio costs seconds, and the answer
        never changes once the stems are written — so it is computed on first
        ask and kept in a file next to them. No schema change, and it works for
        songs separated before this existed.
        """
        import json

        from kord.audio.presence import measure, present_parts

        paths = {n: self.path_for(spotify_id, n) for n in names}
        paths = {n: p for n, p in paths.items() if p is not None}
        if not paths:
            return []

        cache = self.dir_for(spotify_id) / "levels.json"
        levels = {}
        if cache.exists():
            try:
                levels = json.loads(cache.read_text())
            except ValueError:
                levels = {}
        # Recompute if a stem appeared or vanished since the cache was written.
        if set(levels) != set(paths):
            levels = measure(paths)
            cache.write_text(json.dumps(levels))
        return present_parts(levels)
