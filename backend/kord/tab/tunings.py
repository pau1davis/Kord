"""Named tunings as the MIDI note of each open string, lowest string first.

Kord cannot detect tuning (see the phase 3 design, §4) — a band tuned down is
still playing in 12-TET, so the recording is simply in a different key. The
player picks from this table, and every fret number downstream is relative to
their choice.
"""
from __future__ import annotations

# Guitar, low to high.
E_STANDARD = (40, 45, 50, 55, 59, 64)      # E2 A2 D3 G3 B3 E4
EB_STANDARD = (39, 44, 49, 54, 58, 63)
D_STANDARD = (38, 43, 48, 53, 57, 62)
DROP_D = (38, 45, 50, 55, 59, 64)
DROP_C = (36, 43, 48, 53, 57, 62)

# Bass, low to high.
BASS_STANDARD = (28, 33, 38, 43)           # E1 A1 D2 G2
BASS_EB = (27, 32, 37, 42)
BASS_D = (26, 31, 36, 41)
BASS_DROP_D = (26, 33, 38, 43)

TUNINGS: dict[str, tuple[int, ...]] = {
    "E standard": E_STANDARD,
    "Eb standard": EB_STANDARD,
    "D standard": D_STANDARD,
    "Drop D": DROP_D,
    "Drop C": DROP_C,
    "Bass standard": BASS_STANDARD,
    "Bass Eb": BASS_EB,
    "Bass D": BASS_D,
    "Bass Drop D": BASS_DROP_D,
}

# What to assume when the player has not said. Guitar gets the tuning most
# records are in; bass gets its equivalent.
DEFAULT_FOR_PART = {
    "bass": "Bass standard",
    "guitar": "E standard",
    "guitar (left)": "E standard",
    "guitar (right)": "E standard",
}
