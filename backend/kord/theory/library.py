from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Iterable

from kord.models import Analysis
from kord.theory.scales import scale_for

TOP_KEYS = 3


def summarise(analyses: Iterable[Analysis]) -> dict:
    """What your analysed library looks like as a player, not as a database.

    The keys you keep landing in and the tempo range you actually play are the
    two facts that change what you practise, so those are what this reports.
    """
    items = list(analyses)
    keys: Counter[str] = Counter()
    tempos: list[float] = []

    for item in items:
        keys[scale_for(item.key.root, item.key.mode).name] += 1
        # Silence analyses to a tempo of 0. Counting it would anchor the range
        # at zero and make every library look like it spans everything.
        if item.tempo > 0:
            tempos.append(item.tempo)

    tempos.sort()
    return {
        "analyzed": len(items),
        "keys": [
            {"key": name, "count": count}
            for name, count in keys.most_common(TOP_KEYS)
        ],
        "tempo": {
            "min": round(tempos[0]),
            "median": round(median(tempos)),
            "max": round(tempos[-1]),
        } if tempos else None,
    }
