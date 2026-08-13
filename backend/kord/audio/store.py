from __future__ import annotations

import shutil
from pathlib import Path

from kord import db


class AudioStore:
    """Retained playback audio, capped and evicted least-recently-played first.

    Kord plays the file it analysed, which is what makes sync exact. Keeping that
    file is therefore a feature, not a cache of convenience — but it is bounded,
    and an evicted song keeps its analysis and simply re-downloads on next play.
    """

    def __init__(self, root: Path, cap_bytes: int) -> None:
        self.root = Path(root)
        self.cap_bytes = cap_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, spotify_id: str) -> Path | None:
        matches = sorted(self.root.glob(f"{spotify_id}.*"))
        return matches[0] if matches else None

    def retain(self, spotify_id: str, source: Path) -> Path:
        for stale in self.root.glob(f"{spotify_id}.*"):
            stale.unlink()
        destination = self.root / f"{spotify_id}{Path(source).suffix}"
        shutil.copy2(source, destination)
        return destination

    def total_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.root.iterdir() if p.is_file())

    def evict_to_fit(self, conn, incoming_bytes: int) -> list[str]:
        """Delete least-recently-played audio until `incoming_bytes` fits.

        Returns the ids evicted. Analyses are untouched.
        """
        evicted: list[str] = []
        if self.total_bytes() + incoming_bytes <= self.cap_bytes:
            return evicted

        for row in db.audio_tracks_by_least_recently_played(conn):
            path = self.path_for(row["spotify_id"])
            if path is not None:
                path.unlink()
            db.set_audio_ext(conn, row["spotify_id"], None)
            evicted.append(row["spotify_id"])
            if self.total_bytes() + incoming_bytes <= self.cap_bytes:
                break
        return evicted
