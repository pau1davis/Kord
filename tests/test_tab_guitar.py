import pytest

from kord.tab.events import NoteEvent

pytest.importorskip(
    "basic_pitch", reason="guitar transcription is an optional extra")


def test_note_tuples_become_note_events():
    """The adapter's whole job: basic-pitch's tuples into the shared format,
    with amplitude normalised onto the same 0..1 confidence the bass engine
    reports. A number meaning one thing for bass and another for guitar would
    make the dimming in the UI meaningless."""
    from kord.tab.guitar import events_from_notes

    events = events_from_notes([
        (0.0, 0.5, 64, 0.9, []),
        (0.5, 1.0, 67, 0.3, []),
    ])
    assert [e.midi for e in events] == [64, 67]
    assert events[0].confidence > events[1].confidence
    assert all(0.0 <= e.confidence <= 1.0 for e in events)
    assert isinstance(events[0], NoteEvent)


def test_notes_shorter_than_a_grace_note_are_dropped():
    from kord.tab.guitar import events_from_notes
    assert events_from_notes([(0.0, 0.01, 64, 0.9, [])]) == []


def test_notes_come_back_in_time_order():
    """basic-pitch returns notes in confidence order, not time order — the
    earlier probe showed 224s before 220s. Everything downstream assumes time."""
    from kord.tab.guitar import events_from_notes

    events = events_from_notes([
        (2.0, 2.5, 64, 0.9, []),
        (0.5, 1.0, 67, 0.8, []),
        (1.0, 1.5, 60, 0.7, []),
    ])
    assert [e.start_s for e in events] == [0.5, 1.0, 2.0]


def test_simultaneous_notes_are_ordered_by_pitch_not_arbitrarily():
    from kord.tab.guitar import events_from_notes

    events = events_from_notes([
        (0.0, 0.5, 67, 0.9, []),
        (0.0, 0.5, 60, 0.9, []),
    ])
    assert [e.midi for e in events] == [60, 67]


def test_numpy_scalars_from_the_model_become_plain_python():
    """predict() returns numpy types; JSON serialisation later needs floats."""
    import numpy as np

    from kord.tab.guitar import events_from_notes

    events = events_from_notes([
        (np.float64(0.0), np.float64(0.5), np.int64(64), np.float32(0.9), [])])
    assert type(events[0].start_s) is float
    assert type(events[0].midi) is int
    assert type(events[0].confidence) is float


def test_an_amplitude_outside_the_range_is_clamped_not_passed_through():
    from kord.tab.guitar import events_from_notes

    events = events_from_notes([(0.0, 0.5, 64, 1.4, []),
                                (1.0, 1.5, 64, -0.2, [])])
    assert [e.confidence for e in events] == [1.0, 0.0]


def test_no_notes_is_not_a_crash():
    from kord.tab.guitar import events_from_notes
    assert events_from_notes([]) == []
