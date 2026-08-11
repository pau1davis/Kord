from __future__ import annotations

from kord.theory.qualities import NO_CHORD, family_of

_NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII"]
_MAJOR = [0, 2, 4, 5, 7, 9, 11]
_MINOR = [0, 2, 3, 5, 7, 8, 10]
_SUFFIX = {
    "diminished": "°", "augmented": "+", "dim7": "°7", "hdim7": "ø7",
    "dominant7": "7", "major7": "maj7", "minor7": "7",
    "sus2": "sus2", "sus4": "sus4", "power": "5",
}


def roman_numeral(key_root: int, mode: str, chord_root: int, quality: str) -> str:
    if quality == NO_CHORD or chord_root < 0:
        return ""
    scale = _MAJOR if mode == "major" else _MINOR
    interval = (chord_root - key_root) % 12

    if interval in scale:
        index, accidental = scale.index(interval), ""
    elif (interval + 1) % 12 in scale and (interval + 1) % 12 != 0:
        # Spell as a flattened version of the degree above.
        index, accidental = scale.index((interval + 1) % 12), "b"
    else:
        # The degree above wraps to the tonic — spell as a raised degree below
        # instead, so the leading tone in minor reads "#VII" rather than "bI".
        index, accidental = scale.index((interval - 1) % 12), "#"

    numeral = _NUMERALS[index]
    if family_of(quality) in ("minor", "diminished"):
        numeral = numeral.lower()
    return f"{accidental}{numeral}{_SUFFIX.get(quality, '')}"
