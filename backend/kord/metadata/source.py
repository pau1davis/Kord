"""Where song facts come from — never audio, which is AudioSource's job.

Mirrors the AudioSource seam: one module per provider, and the provider module
is the only thing that knows its API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TrackFacts:
    id: str                 # namespaced, see metadata/ids.py
    title: str
    artist: str
    album: str | None
    duration_ms: int
    image: str | None

    def to_dict(self) -> dict:
        """The shape the frontend's TrackSummary already expects."""
        return {
            "id": self.id, "title": self.title, "artist": self.artist,
            "album": self.album, "duration_ms": self.duration_ms,
            "image": self.image,
        }


@runtime_checkable
class MetadataSource(Protocol):
    async def search(self, query: str, limit: int = 20) -> list[TrackFacts]: ...

    async def get(self, track_id: str) -> TrackFacts: ...
