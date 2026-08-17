"""Whether a guitar stem holds one performance or two.

Rock production records a rhythm part twice and hard-pans the takes, so the two
guitarists are already in separate channels. Transcribing them separately is
both more useful — one guitarist at a time is what a learner wants — and an
easier problem, since each channel is closer to monophonic than their sum.

The threshold is duplicated in `frontend/src/stems.ts`, which makes the same
decision for playback. Measured across the library, the two cases do not
overlap: a doubled part reads 0.04 to 0.57 and a single take reads 1.00, so the
two constants agreeing exactly matters less than both sitting in that gap. If a
third caller ever needs it, serve it from the stems endpoint rather than adding
a third copy.
"""
from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

DOUBLE_TRACKED_MAX_CORR = 0.7
SAMPLE_RATE = 22050


def channel_correlation(path: Path) -> float:
    """Pearson correlation between the two channels. 1.0 if there is only one."""
    y, _sr = librosa.load(str(path), sr=SAMPLE_RATE, mono=False)
    if y.ndim == 1 or y.shape[0] < 2:
        return 1.0
    left, right = y[0], y[1]
    # A silent channel has no shape to compare, and calling that "uncorrelated"
    # would advertise a second guitarist who is not there.
    if left.std() < 1e-6 or right.std() < 1e-6:
        return 1.0
    return float(np.corrcoef(left, right)[0, 1])


def split_channels(path: Path, dest_dir: Path) -> list[tuple[str, Path]]:
    """The parts of a guitar stem, as (name, wav path) ready to transcribe.

    WAV rather than m4a: these are scratch inputs for the transcriber, never
    served to a browser, so encoding them would cost time for nothing.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    y, sr = librosa.load(str(path), sr=SAMPLE_RATE, mono=False)

    if abs(channel_correlation(path)) > DOUBLE_TRACKED_MAX_CORR:
        mono = y if y.ndim == 1 else y.mean(axis=0)
        written = dest_dir / "guitar.wav"
        sf.write(written, mono.astype(np.float32), sr)
        return [("guitar", written)]

    parts = []
    for index, name in enumerate(("guitar (left)", "guitar (right)")):
        written = dest_dir / f"{name}.wav"
        sf.write(written, y[index].astype(np.float32), sr)
        parts.append((name, written))
    return parts
