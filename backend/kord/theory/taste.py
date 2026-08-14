from __future__ import annotations

from typing import Iterable

from kord.models import Analysis, PaletteStop
from kord.theory.palette import build_palette


def aggregate_palette(analyses: Iterable[Analysis]) -> list[PaletteStop]:
    """One ring over many songs.

    This is `build_palette` applied to every analysed song's segments at once,
    exactly as the Phase 1 design anticipated — weight is summed duration, so
    a song contributes in proportion to how long its harmony actually sounds.

    Tracks flagged `speed_adjusted` are dropped: a sped-up upload is
    pitch-shifted, so its detected key, and therefore its colour, is unreliable.
    """
    segments = []
    heaviness: list[float] = []
    for analysis in analyses:
        if "speed_adjusted" in analysis.flags:
            continue
        segments.extend(analysis.chord_segments)
        heaviness.append(analysis.heaviness)
    if not segments:
        return []
    mean_heaviness = sum(heaviness) / len(heaviness) if heaviness else 0.0
    return build_palette(segments, mean_heaviness)
