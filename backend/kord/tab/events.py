"""Frame-wise pitch tracks into discrete notes.

Shared by both engines, so nothing downstream knows whether a note came from
pyin or basic-pitch. Pure: takes arrays, returns notes, touches no audio.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class NoteEvent:
    start_s: float
    end_s: float
    midi: int
    confidence: float   # 0..1, meaning the same thing from either engine


def events_from_f0(
    times_s,
    midi_float,
    confidence,
    *,
    min_confidence: float = 0.5,
    min_duration_s: float = 0.06,
    max_gap_s: float = 0.08,
) -> list[NoteEvent]:
    """Merge runs of frames at the same semitone into notes.

    Quantising to the nearest semitone before merging is what makes vibrato and
    intonation drift a single note: a bassist a quarter-tone sharp is playing
    one note, not two. It also means a bend of more than a semitone splits,
    which is a known limitation — articulation is out of scope entirely.
    """
    times_s = np.asarray(times_s, dtype=float)
    midi_float = np.asarray(midi_float, dtype=float)
    confidence = np.asarray(confidence, dtype=float)
    if times_s.size == 0:
        return []

    voiced = np.isfinite(midi_float) & (confidence >= min_confidence)
    semitone = np.where(voiced, np.round(midi_float), np.nan)
    hop = float(np.median(np.diff(times_s))) if times_s.size > 1 else 0.01

    runs: list[tuple[int, int, int]] = []   # (start index, end index, midi)
    start = None
    for i, value in enumerate(semitone):
        if np.isnan(value):
            if start is not None:
                runs.append((start, i, int(semitone[start])))
                start = None
            continue
        if start is None:
            start = i
        elif int(value) != int(semitone[start]):
            runs.append((start, i, int(semitone[start])))
            start = i
    if start is not None:
        runs.append((start, len(semitone), int(semitone[start])))

    # A couple of dropped frames inside a held note is a tracker artefact.
    # Rejoin neighbours of the same pitch separated by less than max_gap_s.
    merged: list[list[int]] = []
    for begin, end, midi in runs:
        if merged and merged[-1][2] == midi and \
                (times_s[begin] - times_s[merged[-1][1] - 1]) <= max_gap_s:
            merged[-1][1] = end
        else:
            merged.append([begin, end, midi])

    events = []
    for begin, end, midi in merged:
        start_s = float(times_s[begin])
        end_s = float(times_s[end - 1]) + hop
        if end_s - start_s < min_duration_s:
            continue
        events.append(NoteEvent(
            start_s=start_s, end_s=end_s, midi=midi,
            confidence=float(np.mean(confidence[begin:end]))))
    return events
