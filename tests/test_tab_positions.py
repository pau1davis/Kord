from kord.tab.positions import Position, assign_positions, candidates
from kord.tab.tunings import BASS_STANDARD, E_STANDARD, TUNINGS


def frets(positions):
    return [p.fret for p in positions if p is not None]


def test_open_low_e_is_the_open_sixth_string():
    assert assign_positions([40], E_STANDARD) == [Position(0, 0)]


def test_a_note_has_every_position_that_can_reach_it():
    # E4 = 64: open first string, 5th fret second, 9th third, 14th fourth...
    places = [(c.string, c.fret) for c in candidates(64, E_STANDARD)]
    assert (5, 0) in places
    assert (4, 5) in places
    assert (3, 9) in places


def test_a_line_is_kept_under_one_hand():
    # The whole reason this is a sequence problem: an A minor pentatonic line
    # is playable without moving, and must not be spread across the neck.
    line = [57, 60, 62, 64, 67, 64, 62, 60]
    played = frets(assign_positions(line, E_STANDARD))
    assert max(played) - min(played) <= 5, played


def test_a_forced_high_note_pulls_its_neighbours_up_the_neck():
    """The case a greedy per-note assignment gets wrong.

    C6 can only be played at the 20th fret. Choosing each note independently
    puts the E4 after it on an open string — a twenty-fret leap between
    consecutive notes, correct on paper and impossible to play.
    """
    played = frets(assign_positions([84, 64], E_STANDARD))
    assert played[0] == 20
    assert played[1] >= 12, played


def test_a_note_below_the_lowest_string_is_unplayable_not_negative():
    # D2 = 38, below the open low E of 40. Never fret -2.
    assert assign_positions([38], E_STANDARD) == [None]


def test_drop_d_reaches_notes_standard_tuning_cannot():
    assert assign_positions([38], TUNINGS["Drop D"]) == [Position(0, 0)]


def test_a_note_above_the_neck_is_unplayable():
    assert assign_positions([120], E_STANDARD) == [None]


def test_unplayable_notes_do_not_break_the_line_around_them():
    played = assign_positions([57, 38, 60], E_STANDARD)
    assert len(played) == 3
    assert played[1] is None
    assert played[0] is not None and played[2] is not None


def test_bass_lines_use_the_bass_tuning():
    # E1 is the open lowest string of a bass, where it is E2 on a guitar.
    assert assign_positions([28], BASS_STANDARD) == [Position(0, 0)]
    assert assign_positions([28], E_STANDARD) == [None]


def test_a_lone_note_goes_to_the_easiest_place_to_reach_it():
    # E2 on a bass is the 2nd fret of the D string, not the 12th of the E.
    # Nothing constrains it, so the low-fret preference decides.
    assert assign_positions([40], BASS_STANDARD) == [Position(2, 2)]


def test_every_named_tuning_is_six_or_four_strings():
    for name, tuning in TUNINGS.items():
        assert len(tuning) in (4, 6), name
        # Drop tunings lower only the lowest string, so strict ascent across
        # the whole set is wrong; everything above the first must still rise.
        assert list(tuning[1:]) == sorted(tuning[1:]), name


def test_an_empty_line_is_not_a_crash():
    assert assign_positions([], E_STANDARD) == []


def test_a_line_of_only_unplayable_notes_is_all_none():
    assert assign_positions([20, 21], E_STANDARD) == [None, None]
