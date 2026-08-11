from __future__ import annotations

from dataclasses import dataclass

_FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
_MAJOR = [0, 2, 4, 5, 7, 9, 11]
_MINOR = [0, 2, 3, 5, 7, 8, 10]


@dataclass(frozen=True)
class ScaleInfo:
    name: str
    notes: list[str]
    suggestions: list[str]


def note_name(pitch_class: int) -> str:
    return _FLAT_NAMES[pitch_class % 12]


def scale_for(key_root: int, mode: str) -> ScaleInfo:
    intervals = _MAJOR if mode == "major" else _MINOR
    tonic = note_name(key_root)
    notes = [note_name(key_root + interval) for interval in intervals]
    if mode == "major":
        relative = note_name(key_root + 9)
        suggestions = [
            f"{tonic} major pentatonic",
            f"{relative} minor",
            f"{tonic} major",
        ]
    else:
        relative = note_name(key_root + 3)
        suggestions = [
            f"{tonic} minor pentatonic",
            f"{tonic} natural minor",
            f"{relative} major",
        ]
    return ScaleInfo(name=f"{tonic} {mode}", notes=notes, suggestions=suggestions)
