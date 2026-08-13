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


import pytest

from kord.analysis.beats import correct_double_time


def env_for(frames, strengths):
    """An onset envelope where `frames[i]` has strength `strengths[i]`."""
    env = np.zeros(int(max(frames)) + 1, dtype=np.float32)
    for f, s in zip(frames, strengths):
        env[f] = s
    return env


def test_halves_a_grid_whose_alternate_beats_are_weak():
    frames = np.arange(0, 160, 10)
    strengths = [10.0 if i % 2 == 0 else 3.0 for i in range(len(frames))]
    out_frames, out_tempo = correct_double_time(
        frames, 184.0, env_for(frames, strengths))
    assert out_tempo == pytest.approx(92.0)
    assert list(out_frames) == list(frames[0::2])


def test_keeps_the_phase_that_carries_the_accents():
    """The strong beats are the odd indices here, so those must survive."""
    frames = np.arange(0, 160, 10)
    strengths = [3.0 if i % 2 == 0 else 10.0 for i in range(len(frames))]
    out_frames, _ = correct_double_time(
        frames, 184.0, env_for(frames, strengths))
    assert list(out_frames) == list(frames[1::2])


def test_leaves_a_uniform_grid_alone():
    frames = np.arange(0, 160, 10)
    strengths = [10.0] * len(frames)
    out_frames, out_tempo = correct_double_time(
        frames, 184.0, env_for(frames, strengths))
    assert out_tempo == pytest.approx(184.0)
    assert list(out_frames) == list(frames)


def test_never_halves_below_the_floor():
    """A true 100 BPM must never become 50, whatever the accents look like."""
    frames = np.arange(0, 160, 10)
    strengths = [10.0 if i % 2 == 0 else 1.0 for i in range(len(frames))]
    out_frames, out_tempo = correct_double_time(
        frames, 100.0, env_for(frames, strengths))
    assert out_tempo == pytest.approx(100.0)
    assert list(out_frames) == list(frames)


def test_too_few_beats_is_left_alone():
    frames = np.array([0, 10])
    out_frames, out_tempo = correct_double_time(
        frames, 184.0, env_for(frames, [10.0, 1.0]))
    assert out_tempo == pytest.approx(184.0)
    assert list(out_frames) == [0, 10]


def test_ambiguous_margin_is_left_alone():
    """0.9 is not a clear enough difference to act on."""
    frames = np.arange(0, 160, 10)
    strengths = [10.0 if i % 2 == 0 else 9.0 for i in range(len(frames))]
    _, out_tempo = correct_double_time(
        frames, 184.0, env_for(frames, strengths))
    assert out_tempo == pytest.approx(184.0)


def test_tempo_and_grid_never_disagree():
    """The two are one fact. A halved tempo with an un-decimated grid would
    draw twice as many beats as it claims."""
    grid = BeatTracker().track(click_track(120.0, 10.0), SR)
    gaps = np.diff(grid.times_s)
    assert abs(60.0 / float(np.median(gaps)) - grid.tempo) < 6.0
