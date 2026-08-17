"""Bass transcription, the only module calling librosa.pyin.

A bass stem is very nearly monophonic, which makes pitch tracking well posed —
the reason this instrument works while polyphonic guitar needed a model and a
measurement. Checked on the separated stems before it was written: 1289 voiced
frames on Superdrag's Wrong vs. Right, stable to a semitone, and the frame
count itself flags the sparse cases.
"""
from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np

from kord.tab.events import NoteEvent, events_from_f0

FMIN_NOTE = "B0"    # below the low B of a five-string
FMAX_NOTE = "G3"    # above anything a bassist frets
SAMPLE_RATE = 22050
HOP_LENGTH = 512


def transcribe_bass(path: Path, *, seconds: float | None = None) -> list[NoteEvent]:
    y, sr = librosa.load(str(path), sr=SAMPLE_RATE, mono=True, duration=seconds)
    if y.size == 0:
        return []
    f0, _voiced, probability = librosa.pyin(
        y, sr=sr,
        fmin=float(librosa.note_to_hz(FMIN_NOTE)),
        fmax=float(librosa.note_to_hz(FMAX_NOTE)),
        frame_length=2048, hop_length=HOP_LENGTH)
    times = librosa.times_like(f0, sr=sr, hop_length=HOP_LENGTH)
    with np.errstate(invalid="ignore", divide="ignore"):
        midi = librosa.hz_to_midi(f0)
    return events_from_f0(times, midi, np.nan_to_num(probability))
