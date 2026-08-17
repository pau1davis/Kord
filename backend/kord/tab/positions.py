"""Where on the neck to play each note.

The problem this solves: E3 sits in five places on a guitar. Choosing each
note's position independently produces tab that leaps the length of the neck
between consecutive notes — technically correct, unplayable, and worse than
nothing because it looks authoritative. So the whole sequence is assigned at
once, by shortest path.
"""
from __future__ import annotations

from dataclasses import dataclass

# Cost weights. Movement dominates: everything else is a tiebreak between
# positions the hand can reach without travelling.
MOVE_COST = 1.0
HIGH_FRET_COST = 0.08     # mild preference for the low neck, where a learner is
OPEN_STRING_BONUS = 0.5   # an open string needs no finger

# The dusty end of an ordinary electric. Lower would make notes unplayable that
# plainly are not — C6 is the 20th fret of the top string.
MAX_FRET = 22


@dataclass(frozen=True)
class Position:
    string: int   # 0 = lowest-pitched string
    fret: int


def candidates(midi: int, tuning, max_fret: int = MAX_FRET) -> list[Position]:
    """Every place this note can be played in this tuning."""
    return [Position(string, midi - open_midi)
            for string, open_midi in enumerate(tuning)
            if 0 <= midi - open_midi <= max_fret]


def _step_cost(previous: Position | None, position: Position) -> float:
    cost = HIGH_FRET_COST * position.fret
    if position.fret == 0:
        cost -= OPEN_STRING_BONUS
    if previous is not None:
        # Distance is measured on fret numbers including zero: an open string
        # is at the nut, and reaching the nut from the 20th fret is a journey
        # whether or not a finger lands.
        cost += MOVE_COST * abs(position.fret - previous.fret)
    return cost


def assign_positions(
    midis, tuning, *, max_fret: int = MAX_FRET,
) -> list[Position | None]:
    """Positions for a sequence of notes, chosen together.

    Notes with nowhere to be played — below the lowest open string, or off the
    end of the neck — come back as None rather than a negative fret. They are
    left in place so callers can count them: a lot of them means the tuning is
    wrong, which is worth knowing rather than hiding.
    """
    # Viterbi over the playable notes. Unplayable ones break no chain: the
    # previous playable position simply carries across the gap, so a line is
    # still assigned as one hand movement either side of a note it cannot play.
    best: dict[Position, tuple[float, list[Position | None]]] = {}
    prefix: list[Position | None] = []
    started = False

    for midi in midis:
        choices = candidates(midi, tuning, max_fret)
        if not choices:
            if started:
                best = {p: (cost, path + [None]) for p, (cost, path) in best.items()}
            else:
                prefix.append(None)
            continue
        if not started:
            best = {c: (_step_cost(None, c), prefix + [c]) for c in choices}
            started = True
            continue
        best = {
            choice: min(
                ((cost + _step_cost(previous, choice), path + [choice])
                 for previous, (cost, path) in best.items()),
                key=lambda pair: pair[0])
            for choice in choices
        }

    if not started:
        return prefix
    return min(best.values(), key=lambda pair: pair[0])[1]
