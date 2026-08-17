"""Guitar transcription, the only module importing basic-pitch.

Polyphonic, because a guitar plays chords — the reason bass could use pyin and
this could not. Measured before it was written; see
docs/notes/2026-08-17-transcription-accuracy.md. The short version:
it finds what was played and adds extras, and high-gain power-chord material is
the weak case. That is why every note carries a confidence and the interface
dims the doubtful ones.
"""
from __future__ import annotations

from pathlib import Path

from kord.tab.events import NoteEvent

MIN_DURATION_S = 0.06


def events_from_notes(notes) -> list[NoteEvent]:
    """basic-pitch note tuples into the shared format.

    Tuples are `(start_s, end_s, midi, amplitude, bends)` with numpy scalars
    throughout, so everything is converted to plain Python — these are JSON
    serialised later, and numpy types are not.

    Amplitude is already 0..1 and becomes confidence directly, which puts it on
    the same scale as pyin's voiced probability.
    """
    events = []
    for start_s, end_s, midi, amplitude, *_ in notes:
        if float(end_s) - float(start_s) < MIN_DURATION_S:
            continue
        events.append(NoteEvent(
            start_s=float(start_s), end_s=float(end_s), midi=int(midi),
            confidence=min(1.0, max(0.0, float(amplitude)))))
    # By time, then pitch. The model returns notes in roughly descending
    # confidence — the first probe gave 224s before 220s — and everything
    # downstream, from bar grouping to position assignment, assumes time order.
    return sorted(events, key=lambda e: (e.start_s, e.midi))


def transcribe_guitar(path: Path) -> list[NoteEvent]:
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict

    _model_output, _midi, notes = predict(str(path), ICASSP_2022_MODEL_PATH)
    return events_from_notes(notes)
