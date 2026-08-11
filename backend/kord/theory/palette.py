from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from kord.models import ChordSegment, PaletteStop
from kord.theory.qualities import NO_CHORD, hue_for


def build_palette(segments: Iterable[ChordSegment]) -> list[PaletteStop]:
    """Weight each hue by how long it sounds. Works for one song or many.

    Phase 3's aggregate ring over the whole listening history is this same
    function applied to the concatenated segments of every analyzed track.
    """
    weights: dict[int, float] = defaultdict(float)
    total = 0.0
    for segment in segments:
        if segment.quality == NO_CHORD or segment.root < 0:
            continue
        duration = segment.duration_s
        if duration <= 0:
            continue
        weights[hue_for(segment.quality)] += duration
        total += duration
    if total == 0:
        return []
    stops = [PaletteStop(hue=hue, weight=weight / total) for hue, weight in weights.items()]
    return sorted(stops, key=lambda stop: (-stop.weight, stop.hue))
