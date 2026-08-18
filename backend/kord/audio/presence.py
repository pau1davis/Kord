"""Which separated parts are actually in the song.

htdemucs_6s always emits all six stems whether or not the song has a piano, so
an empty fader is indistinguishable from a quiet one. Six of nine songs in the
library have a piano stem that is pure separation bleed.

Deliberately a conservative gate rather than instrument identification. Measured
across the library, levels form a continuum, not two clusters:

    -67 -65 -63 -62 | -51 -48 -47 | -40 | -32 -31 -30 -28 -27 -26 -25 | -18 ...

Below about -45 dB nothing is there. Above about -20 dB something is. In
between is genuinely ambiguous, because Demucs bleed is a real low-level copy
of the other instruments and looks much like a quiet real part. So the floor
sits well clear of anything real — Sebadoh's bass, the quietest genuine part in
the library, is 7.6 dB above it — and anything uncertain is kept. A fader that
plays near silence is a small annoyance; hiding a part that is really there is
worse.
"""
from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np

# Relative to the loudest stem in the same song, so mastering level cancels.
SILENCE_FLOOR_DB = -40.0
# Level only, so the sample rate can be low. A whole song at 8kHz costs little.
MEASURE_SR = 8000


def level_db(path: Path) -> float:
    """RMS level of a stem in dBFS, or -99 for silence.

    A file that will not decode reports 0.0 — the loudest possible — so it is
    kept rather than hidden. Failing to measure a part is not evidence that the
    part is absent, and hiding a real one is the worse mistake.
    """
    try:
        y, _sr = librosa.load(str(path), sr=MEASURE_SR, mono=True)
    except Exception:
        return 0.0
    if y.size == 0:
        return -99.0
    rms = float(np.sqrt(np.mean(np.square(y))))
    return 20 * float(np.log10(rms)) if rms > 0 else -99.0


def present_parts(
    levels_db: dict[str, float], floor_db: float = SILENCE_FLOOR_DB
) -> list[str]:
    """The parts loud enough to be in the song, in the order given.

    Measured against the loudest stem rather than an absolute level, so a
    quietly mastered song does not lose every part at once.
    """
    if not levels_db:
        return []
    loudest = max(levels_db.values())
    return [name for name, level in levels_db.items()
            if level - loudest >= floor_db]


def measure(paths: dict[str, Path]) -> dict[str, float]:
    """Level of every stem, whole song. Slow enough to be worth caching."""
    return {name: level_db(path) for name, path in paths.items()}
