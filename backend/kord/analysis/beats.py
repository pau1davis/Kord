from __future__ import annotations

import librosa
import numpy as np

from kord.models import BeatGrid


DOUBLE_TIME_FLOOR_BPM = 130.0
PHASE_MARGIN = 0.85


def correct_double_time(
    frames: np.ndarray,
    tempo: float,
    onset_env: np.ndarray,
    *,
    floor_bpm: float = DOUBLE_TIME_FLOOR_BPM,
    margin: float = PHASE_MARGIN,
) -> tuple[np.ndarray, float]:
    """Halve a double-time grid, keeping the phase that carries the accents.

    A doubled grid always fits the audio, because the true beats are a subset
    of it — goodness-of-fit therefore cannot tell 92 BPM from 184. What can is
    which beats carry onset energy: in a doubled grid every other beat falls
    between the real ones and is measurably weaker.

    Known confound, deliberately bounded rather than solved: a backbeat (snare
    on 2 and 4) produces the same alternating asymmetry without being
    double-time. `floor_bpm` and `margin` exist to keep that from firing on
    ordinary rock, and on anything ambiguous the grid is returned untouched.
    See docs/notes/2026-08-13-tempo-calibration.md for the
    measured values.
    """
    if tempo < floor_bpm or len(frames) < 4:
        return frames, tempo

    strength = onset_env[np.clip(frames, 0, len(onset_env) - 1)]
    even, odd = strength[0::2], strength[1::2]
    if even.size == 0 or odd.size == 0:
        return frames, tempo

    even_mean, odd_mean = float(even.mean()), float(odd.mean())
    strong = max(even_mean, odd_mean)
    weak = min(even_mean, odd_mean)
    if strong <= 0 or weak / strong > margin:
        return frames, tempo

    phase = 0 if even_mean >= odd_mean else 1
    return frames[phase::2], tempo / 2.0


class BeatTracker:
    """Beat grid and tempo.

    Phase 1 stores these but does not display them; Phase 2's scrolling chart
    needs the grid, and by then the decoded audio is long gone.
    """

    def track(self, y: np.ndarray, sr: int) -> BeatGrid:
        if not np.any(np.abs(y) > 1e-6):
            return BeatGrid(times_s=[], tempo=0.0)
        tempo, frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
        times = librosa.frames_to_time(frames, sr=sr)
        return BeatGrid(
            times_s=[float(t) for t in times],
            tempo=float(np.atleast_1d(tempo)[0]),
        )
