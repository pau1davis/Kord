from __future__ import annotations

from dataclasses import dataclass

_FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
_SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_MAJOR = [0, 2, 4, 5, 7, 9, 11]
_MINOR = [0, 2, 3, 5, 7, 8, 10]

# Major keys conventionally written with sharps: G D A E B F#. Everything else
# takes flats. C# major (7 sharps) is spelled Db, and F# is preferred over Gb
# because guitarists meet it far more often.
_SHARP_MAJOR_TONICS = {7, 2, 9, 4, 11, 6}


@dataclass(frozen=True)
class ScaleInfo:
    name: str
    notes: list[str]
    suggestions: list[str]


def uses_sharps(key_root: int, mode: str) -> bool:
    """Whether a key is conventionally spelled with sharps rather than flats.

    A minor key inherits the spelling of its relative major, so E minor takes
    sharps (relative G) while D minor takes flats (relative F).
    """
    relative_major = key_root % 12 if mode == "major" else (key_root + 3) % 12
    return relative_major in _SHARP_MAJOR_TONICS


def note_name(pitch_class: int, prefer_sharps: bool = False) -> str:
    names = _SHARP_NAMES if prefer_sharps else _FLAT_NAMES
    return names[pitch_class % 12]


def scale_for(key_root: int, mode: str) -> ScaleInfo:
    intervals = _MAJOR if mode == "major" else _MINOR
    sharps = uses_sharps(key_root, mode)
    tonic = note_name(key_root, sharps)
    notes = [note_name(key_root + interval, sharps) for interval in intervals]
    if mode == "major":
        relative = note_name(key_root + 9, sharps)
        suggestions = [
            f"{tonic} major pentatonic",
            f"{relative} minor",
            f"{tonic} major",
        ]
    else:
        relative = note_name(key_root + 3, sharps)
        suggestions = [
            f"{tonic} minor pentatonic",
            f"{tonic} natural minor",
            f"{relative} major",
        ]
    return ScaleInfo(name=f"{tonic} {mode}", notes=notes, suggestions=suggestions)
