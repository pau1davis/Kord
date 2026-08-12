from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from kord.models import ChordSegment, PaletteStop
from kord.theory.qualities import NO_CHORD, hue_for


HEAVY_HUE = 0
# The largest share of the ring heaviness alone may claim. Capped so the harmony
# is always visible: a wall of distortion should tint the song, not erase it.
MAX_HEAVY_SHARE = 0.7


def build_palette(
    segments: Iterable[ChordSegment], heaviness: float = 0.0
) -> list[PaletteStop]:
    """Weight each hue by how long it sounds. Works for one song or many.

    `heaviness` (0-1) blends red in proportionally rather than reclassifying
    chords. Distortion cannot be told apart from loudness-war mastering by any
    measured feature, so a continuous blend degrades gracefully where a binary
    class would be confidently wrong.

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

    shares = {hue: weight / total for hue, weight in weights.items()}

    red_share = max(0.0, min(1.0, heaviness)) * MAX_HEAVY_SHARE
    if red_share > 0:
        # Make room proportionally, then fold red in — merging with any power
        # chords already sitting on that hue rather than adding a second stop.
        shares = {hue: share * (1 - red_share) for hue, share in shares.items()}
        shares[HEAVY_HUE] = shares.get(HEAVY_HUE, 0.0) + red_share

    stops = [PaletteStop(hue=hue, weight=share) for hue, share in shares.items()]
    return sorted(stops, key=lambda stop: (-stop.weight, stop.hue))
