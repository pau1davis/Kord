"""How far the record sits from A440, and how low it is played.

What is *not* here is a named tuning. A band tuned a whole step down is still
playing in 12-TET; the recording is simply in a different key, so the tuning
itself leaves no trace in the audio. The lowest note played is a lower bound on
the lowest string and nothing more — a song in E standard that never sounds an
open low E is indistinguishable from one tuned higher. Naming a tuning from
that would be a guess wearing the clothes of a measurement.

Two things are genuinely measurable, and both are useful on their own:

- **Reference pitch.** Records are not all at A440 — tape speed drifts, and
  plenty of bands tune deliberately flat. This is the number that explains why
  a perfectly tuned guitar sounds wrong against the record.
- **Lowest note played** (`lowest.py`, from an isolated bass stem), which tells
  a player how far down the song actually goes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import librosa
import numpy as np

WINDOW_S = 30.0
# Below this level of agreement between windows the number means nothing —
# either the song has no stable pitch reference or the windows disagree wildly.
TRUSTWORTHY_AGREEMENT = 0.5


@dataclass(frozen=True)
class ReferencePitch:
    cents: float       # deviation from A440, in [-50, 50)
    agreement: float   # 0..1, how tightly the windows agreed

    @property
    def trustworthy(self) -> bool:
        return self.agreement >= TRUSTWORTHY_AGREEMENT


def circular_average(fractions: list[float] | np.ndarray) -> tuple[float, float]:
    """Average of values on a circle, plus how tightly they cluster.

    `estimate_tuning` reports a fraction of a semitone in [-0.5, 0.5), where
    -0.5 and +0.5 are the same pitch. Averaging those arithmetically is wrong
    in the one case that matters most: Pantera's Mouth for War reads
    49, 49, 48, 47, -43, -50, 42 across its windows, which is one value sitting
    on the wraparound, but a plain mean calls it +20 and a plain spread calls it
    a 99-cent disagreement.

    Returns (fraction in [-0.5, 0.5), resultant length in [0, 1]).
    """
    values = np.asarray(list(fractions), dtype=float)
    if values.size == 0:
        return 0.0, 0.0
    # One semitone is one full turn, so -0.5 and +0.5 land on the same point.
    angles = 2 * math.pi * values
    cos, sin = float(np.cos(angles).mean()), float(np.sin(angles).mean())
    resultant = math.hypot(cos, sin)
    if resultant < 1e-12:
        return 0.0, 0.0
    mean_angle = math.atan2(sin, cos)
    # Median of the values rotated so the mean sits at zero, then rotated back:
    # keeps the median's resistance to outliers without letting the wraparound
    # decide the answer.
    centred = np.angle(np.exp(1j * (angles - mean_angle)))
    angle = mean_angle + float(np.median(centred))
    fraction = ((angle / (2 * math.pi)) + 0.5) % 1.0 - 0.5
    return fraction, resultant


def estimate_reference(y: np.ndarray, sr: int, window_s: float = WINDOW_S
                       ) -> ReferencePitch:
    """Deviation from A440, measured in windows and combined circularly.

    Windowed rather than measured once over the whole song so that the spread
    between windows can be reported: a single number over four minutes has no
    way to say how sure it is.
    """
    step = int(window_s * sr)
    if step <= 0 or y.size == 0:
        return ReferencePitch(0.0, 0.0)
    windows = [y[i:i + step] for i in range(0, y.size, step)]
    # A stub of a window at the end estimates poorly; drop it unless it is all
    # there is.
    full = [w for w in windows if w.size >= step // 2] or windows

    # Windows with nothing in them have to be dropped, not averaged. Given
    # silence librosa finds no pitches and returns 0.0, and a run of those
    # agrees with itself perfectly — the result was a confident reading of
    # "exactly A440" taken from no evidence at all, which is worse than
    # admitting there is none.
    overall = float(np.sqrt(np.mean(np.square(y)))) if y.size else 0.0
    floor = max(1e-4, 0.01 * overall)
    pitched = [w for w in full if float(np.sqrt(np.mean(np.square(w)))) > floor]
    if not pitched:
        return ReferencePitch(0.0, 0.0)

    fractions = [float(librosa.estimate_tuning(y=w, sr=sr)) for w in pitched]
    fraction, agreement = circular_average(fractions)
    return ReferencePitch(cents=fraction * 100.0, agreement=agreement)
