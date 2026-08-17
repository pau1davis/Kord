import numpy as np
import pytest

from kord.tab.events import NoteEvent, events_from_f0


def track(pairs, hop=0.01):
    """pairs: list of (midi_or_None, frames). Builds a frame-wise F0 track."""
    midi, conf = [], []
    for value, frames in pairs:
        midi += [np.nan if value is None else value] * frames
        conf += [0.0 if value is None else 0.9] * frames
    times = np.arange(len(midi)) * hop
    return times, np.array(midi, dtype=float), np.array(conf)


def test_a_steady_pitch_becomes_one_note():
    events = events_from_f0(*track([(45.0, 50)]))
    assert len(events) == 1
    assert events[0].midi == 45
    assert events[0].end_s - events[0].start_s > 0.4


def test_a_change_of_pitch_starts_a_new_note():
    events = events_from_f0(*track([(45.0, 40), (47.0, 40)]))
    assert [e.midi for e in events] == [45, 47]


def test_small_wobble_within_a_semitone_does_not_split_the_note():
    # Vibrato and intonation drift are not note changes.
    events = events_from_f0(*track([(45.1, 20), (44.8, 20), (45.2, 20)]))
    assert [e.midi for e in events] == [45]


def test_an_unvoiced_gap_ends_the_note():
    events = events_from_f0(*track([(45.0, 40), (None, 30), (45.0, 40)]))
    assert len(events) == 2


def test_a_gap_too_short_to_hear_does_not_split_a_held_note():
    # A couple of dropped frames mid-note is a tracker artefact, not silence.
    events = events_from_f0(*track([(45.0, 40), (None, 3), (45.0, 40)]))
    assert len(events) == 1


def test_notes_too_short_to_play_are_dropped():
    events = events_from_f0(*track([(45.0, 2), (47.0, 60)]))
    assert [e.midi for e in events] == [47]


def test_low_confidence_frames_are_not_notes():
    times, midi, conf = track([(45.0, 60)])
    conf[:] = 0.1
    assert events_from_f0(times, midi, conf) == []


def test_confidence_is_carried_through_as_the_frame_average():
    times, midi, conf = track([(45.0, 60)])
    conf[:] = 0.7
    assert events_from_f0(times, midi, conf)[0].confidence == pytest.approx(
        0.7, abs=0.01)


def test_an_empty_track_is_not_a_crash():
    assert events_from_f0(np.array([]), np.array([]), np.array([])) == []


def test_events_come_back_in_time_order():
    events = events_from_f0(*track([(45.0, 40), (47.0, 40), (43.0, 40)]))
    assert [e.start_s for e in events] == sorted(e.start_s for e in events)


def test_transcribe_bass_finds_a_synthesised_note(tmp_path):
    """End to end on audio whose pitch is known exactly."""
    import soundfile as sf

    from kord.tab.bass import transcribe_bass

    sr = 22050
    t = np.arange(int(sr * 2.0)) / sr
    freq = 440.0 * 2 ** ((45 - 69) / 12)          # A2, an open bass A at fret 12
    y = sum(np.sin(2 * np.pi * freq * h * t) / h for h in (1, 2, 3))
    path = tmp_path / "bass.wav"
    sf.write(path, (y / np.abs(y).max()).astype(np.float32), sr)

    events = transcribe_bass(path)
    assert events, "no notes found in a two-second sustained tone"
    assert events[0].midi == 45
