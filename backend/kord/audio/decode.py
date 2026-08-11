from __future__ import annotations

import subprocess
from pathlib import Path

import librosa
import numpy as np

SAMPLE_RATE = 22050


def decode_to_wav(src: Path, dst: Path, sample_rate: int = SAMPLE_RATE) -> Path:
    """Decode any container to mono WAV at the analysis sample rate."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-ac", "1", "-ar", str(sample_rate), str(dst)],
        check=True,
    )
    return dst


def trim_leading_silence(
    y: np.ndarray, sr: int, threshold_db: float = 40.0
) -> tuple[np.ndarray, int]:
    """Drop leading silence. Returns (trimmed_audio, trimmed_milliseconds).

    The trimmed amount is the initial sync offset — YouTube uploads often carry
    intro padding the Spotify master does not have.

    Boundaries are frame-quantized, so the cut lands just before the true onset
    (within one ~23 ms frame) rather than exactly on it. That errs in the safe
    direction: a few milliseconds of retained silence is imperceptible, whereas
    clipping a song's first note is not. Phase 2's manual nudge slider absorbs
    the remaining error.
    """
    intervals = librosa.effects.split(y, top_db=threshold_db)
    if len(intervals) == 0:
        return y, 0                      # entirely silent: leave it alone
    start_sample = int(intervals[0][0])
    if start_sample <= 0:
        return y, 0
    return y[start_sample:], int(round(start_sample / sr * 1000))
