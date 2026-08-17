from kord.tab.bars import bar_starts, group_into_bars
from kord.tab.events import NoteEvent


def note(start, midi=45):
    return NoteEvent(start_s=start, end_s=start + 0.2, midi=midi, confidence=0.9)


def test_four_beats_make_a_bar():
    beats = [i * 0.5 for i in range(12)]
    assert bar_starts(beats) == [0.0, 2.0, 4.0]


def test_a_song_with_no_beat_grid_is_one_long_bar():
    # Better than refusing to render: the notes are still right.
    assert bar_starts([]) == [0.0]


def test_notes_land_in_the_bar_they_start_in():
    beats = [i * 0.5 for i in range(12)]
    bars = group_into_bars([note(0.1), note(2.1), note(2.6)], bar_starts(beats))
    assert [len(b) for b in bars] == [1, 2, 0]


def test_a_note_before_the_first_beat_is_not_lost():
    # Pickup notes exist, and dropping them silently would be wrong.
    bars = group_into_bars([note(0.0)], [0.5, 2.5])
    assert len(bars[0]) == 1


def test_bars_come_back_even_when_empty():
    assert group_into_bars([], [0.0, 2.0, 4.0]) == [[], [], []]


def test_every_note_ends_up_somewhere():
    beats = [i * 0.5 for i in range(12)]
    notes = [note(t) for t in (0.0, 1.9, 2.0, 3.99, 4.0, 99.0)]
    bars = group_into_bars(notes, bar_starts(beats))
    assert sum(len(b) for b in bars) == len(notes)


def test_a_three_four_song_is_barred_wrongly_but_not_dropped():
    """4/4 is assumed project-wide, so a waltz gets its lines in the wrong
    places. The notes must still all be there — wrong bar lines are readable,
    missing notes are not."""
    beats = [i * 0.5 for i in range(12)]
    bars = group_into_bars([note(i * 0.5) for i in range(12)], bar_starts(beats))
    assert sum(len(b) for b in bars) == 12
