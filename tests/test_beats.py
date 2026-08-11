import numpy as np

from kord.analysis.beats import BeatTracker

SR = 22050


def click_track(bpm: float, seconds: float, sr: int = SR) -> np.ndarray:
    """Percussive bursts with a sharp attack and broadband content.

    A bare windowed pulse is too clean for librosa's onset detection to latch
    onto — it yields zero beats. Noise bursts with exponential decay behave like
    real percussion, which is what the tracker is built for.
    """
    rng = np.random.default_rng(0)
    y = np.zeros(int(seconds * sr), dtype=np.float32)
    interval = int(sr * 60.0 / bpm)
    length = 2048
    decay = np.exp(-np.arange(length) / (sr * 0.02)).astype(np.float32)
    for start in range(0, len(y) - length, interval):
        y[start:start + length] += rng.standard_normal(length).astype(np.float32) * decay
    return y / np.max(np.abs(y))


def test_detects_tempo_of_a_click_track_within_tolerance():
    grid = BeatTracker().track(click_track(120.0, 10.0), SR)
    assert abs(grid.tempo - 120.0) < 12.0


def test_detects_a_range_of_tempos():
    for bpm in (90.0, 150.0):
        grid = BeatTracker().track(click_track(bpm, 10.0), SR)
        assert abs(grid.tempo - bpm) < 12.0, f"{bpm} -> {grid.tempo}"


def test_beat_times_are_increasing_and_within_bounds():
    grid = BeatTracker().track(click_track(100.0, 8.0), SR)
    assert grid.times_s == sorted(grid.times_s)
    assert all(0 <= t <= 8.1 for t in grid.times_s)


def test_silence_returns_an_empty_grid_without_crashing():
    grid = BeatTracker().track(np.zeros(SR, dtype=np.float32), SR)
    assert grid.times_s == []
    assert grid.tempo == 0.0


def test_tempo_is_a_plain_float_not_an_array():
    """Guards against librosa returning a 1-element array, which breaks JSON."""
    grid = BeatTracker().track(click_track(120.0, 6.0), SR)
    assert isinstance(grid.tempo, float)
    assert all(isinstance(t, float) for t in grid.times_s)
