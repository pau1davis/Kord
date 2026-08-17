"""The player's own correction to a tempo the tracker got wrong.

Detecting half-time from audio was measured and abandoned (see
docs/notes/2026-08-13-tempo-calibration.md): most rock plays the
eighths, so nothing distinguishes a missed beat from a subdivision. The player
knows the song, so they get the control instead.
"""
import pytest

from kord.analysis.beats import ALLOWED_FACTORS, apply_tempo_factor


def test_one_changes_nothing():
    tempo, beats = apply_tempo_factor(92.0, [0.0, 0.65, 1.3], 1.0)
    assert tempo == 92.0
    assert beats == [0.0, 0.65, 1.3]


def test_doubling_fills_in_the_beats_between():
    """The grid has to double with the number, or the metronome strip stops
    matching the tempo beside it."""
    tempo, beats = apply_tempo_factor(68.0, [0.0, 1.0, 2.0], 2.0)
    assert tempo == 136.0
    assert beats == [0.0, 0.5, 1.0, 1.5, 2.0]


def test_halving_drops_every_other_beat():
    tempo, beats = apply_tempo_factor(172.0, [0.0, 0.5, 1.0, 1.5, 2.0], 0.5)
    assert tempo == 86.0
    assert beats == [0.0, 1.0, 2.0]


def test_halving_keeps_the_downbeat_rather_than_the_offbeat():
    # Dropping the first beat would shift the whole grid off the music.
    _, beats = apply_tempo_factor(160.0, [0.25, 0.75, 1.25, 1.75], 0.5)
    assert beats[0] == 0.25


def test_an_uneven_grid_still_doubles_between_each_pair():
    # Live playing drifts; the midpoint is per gap, not one global spacing.
    _, beats = apply_tempo_factor(60.0, [0.0, 1.0, 2.4], 2.0)
    assert beats == [0.0, 0.5, 1.0, 1.7, 2.4]


def test_a_grid_too_short_to_halve_is_left_alone():
    tempo, beats = apply_tempo_factor(120.0, [0.5], 0.5)
    assert tempo == 60.0
    assert beats == [0.5]


def test_no_grid_at_all_is_not_a_crash():
    assert apply_tempo_factor(120.0, [], 2.0) == (240.0, [])


def test_only_sane_factors_are_offered():
    # A free-text multiplier invites 1.03 and a grid that matches nothing.
    assert ALLOWED_FACTORS == (0.5, 1.0, 2.0)


def test_an_unknown_factor_is_refused_rather_than_applied():
    with pytest.raises(ValueError):
        apply_tempo_factor(120.0, [0.0, 0.5], 1.5)
