"""Note events on disk, one JSON file per song and part.

Note events rather than fret positions: positions depend on the tuning the
player picks, and re-deriving them is instant while re-transcribing is not.
"""
from __future__ import annotations

import json
from pathlib import Path

from kord.tab.events import NoteEvent

# The instruments tab is for, in display order. Guitar splits into two parts
# when the stem turns out to be double-tracked.
PARTS = ("bass", "guitar", "guitar (left)", "guitar (right)")


class TabStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, spotify_id: str, part: str) -> Path:
        # Whitelist, not sanitisation: `part` arrives as a URL path segment,
        # and a whitelist cannot be talked out of by a traversal sequence.
        if part not in PARTS:
            raise ValueError(f"unknown tab part: {part!r}")
        return self.root / spotify_id / f"{part}.json"

    def save(self, spotify_id: str, part: str, events: list[NoteEvent]) -> Path:
        path = self.path_for(spotify_id, part)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([
            {"start_s": e.start_s, "end_s": e.end_s,
             "midi": e.midi, "confidence": e.confidence}
            for e in events]))
        return path

    def load(self, spotify_id: str, part: str) -> list[NoteEvent]:
        path = self.path_for(spotify_id, part)
        if not path.exists():
            return []
        return [NoteEvent(**row) for row in json.loads(path.read_text())]

    def parts(self, spotify_id: str) -> list[str]:
        """Which parts have been transcribed, in display order.

        A part with no notes still counts as transcribed — the file exists.
        Treating "no notes" as "never ran" would retranscribe it forever.
        """
        return [p for p in PARTS if self.path_for(spotify_id, p).exists()]
