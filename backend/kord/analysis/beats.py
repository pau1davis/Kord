from __future__ import annotations

import librosa
import numpy as np

from kord.models import BeatGrid


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
