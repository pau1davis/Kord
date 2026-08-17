"""Bar lines from the beat grid Kord already tracks.

4/4 assumed throughout, because nothing in Kord detects time signature. A song
in 3/4 gets its bar lines in the wrong places while every note and position
stays correct — the tab is still readable, just barred wrongly, and the UI says
so rather than pretending.
"""
from __future__ import annotations

from kord.tab.events import NoteEvent

BEATS_PER_BAR = 4


def bar_starts(beat_times, beats_per_bar: int = BEATS_PER_BAR) -> list[float]:
    """The time each bar begins."""
    if len(beat_times) == 0:
        # No grid is not a reason to render nothing; it is a reason to render
        # one unbroken bar.
        return [0.0]
    return [float(t) for t in beat_times[::beats_per_bar]]


def group_into_bars(events, starts) -> list[list[NoteEvent]]:
    """Each note in the bar it starts in. Bars with no notes come back empty.

    A note before the first bar line — a pickup, or one nudged early by the
    sync offset — goes into the first bar rather than being dropped.
    """
    bars: list[list[NoteEvent]] = [[] for _ in starts]
    for event in events:
        index = 0
        for i, start in enumerate(starts):
            if event.start_s >= start:
                index = i
        bars[index].append(event)
    return bars
