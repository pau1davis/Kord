from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChordSegment:
    start_s: float
    end_s: float
    root: int          # pitch class 0-11; -1 means "no chord"
    quality: str       # canonical quality, see theory/qualities.py
    confidence: float

    def __post_init__(self) -> None:
        if self.end_s < self.start_s:
            raise ValueError(f"end_s {self.end_s} precedes start_s {self.start_s}")

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass(frozen=True)
class KeyEstimate:
    root: int
    mode: str          # "major" | "minor"
    confidence: float
    agreed: bool       # did the two independent estimators agree?


@dataclass(frozen=True)
class BeatGrid:
    times_s: list[float]
    tempo: float


@dataclass(frozen=True)
class AudioCandidate:
    path: str | None
    url: str
    duration_ms: int
    title: str


@dataclass(frozen=True)
class PaletteStop:
    hue: int
    weight: float


@dataclass
class Analysis:
    spotify_id: str
    engine_version: str
    key: KeyEstimate
    tempo: float
    beat_grid: BeatGrid
    chord_segments: list[ChordSegment]
    source_url: str
    source_duration_ms: int
    time_scale: float
    sync_offset_ms: int
    flags: list[str] = field(default_factory=list)
    chord_confidence_mean: float = 0.0
    heaviness: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Analysis":
        return cls(
            spotify_id=d["spotify_id"],
            engine_version=d["engine_version"],
            key=KeyEstimate(**d["key"]),
            tempo=d["tempo"],
            beat_grid=BeatGrid(**d["beat_grid"]),
            chord_segments=[ChordSegment(**s) for s in d["chord_segments"]],
            source_url=d["source_url"],
            source_duration_ms=d["source_duration_ms"],
            time_scale=d["time_scale"],
            sync_offset_ms=d["sync_offset_ms"],
            flags=list(d.get("flags", [])),
            chord_confidence_mean=d.get("chord_confidence_mean", 0.0),
            heaviness=d.get("heaviness", 0.0),
        )
