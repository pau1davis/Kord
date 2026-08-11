from __future__ import annotations

NO_CHORD = "none"

_PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

_ALIASES = {
    "maj": "major", "": "major", "M": "major",
    "min": "minor", "m": "minor",
    "dim": "diminished", "aug": "augmented",
    "maj7": "major7", "min7": "minor7", "7": "dominant7",
    "dim7": "dim7", "hdim7": "hdim7",
    "sus2": "sus2", "sus4": "sus4", "5": "power",
}

# Hues fixed by spec section 7.
_HUES = {
    "power": 0, "dominant7": 30, "major": 40, "major7": 40,
    "sus2": 170, "sus4": 170, "minor": 220, "minor7": 220,
    "diminished": 285, "augmented": 285, "dim7": 285, "hdim7": 285,
}
_FAMILY_HUES = {
    "power": 0, "major": 40, "minor": 220,
    "diminished": 285, "augmented": 285, "sus": 170,
}


def parse_label(label: str) -> tuple[int, str]:
    """Parse 'C:maj', 'F#:hdim7', 'Bb:7', 'C', 'N' into (pitch_class, quality)."""
    label = label.strip()
    if label in ("N", "X", ""):
        return (-1, NO_CHORD)
    root_part, _, quality_part = label.partition(":")
    if not root_part or root_part[0] not in _PITCH:
        return (-1, NO_CHORD)
    pitch_class = _PITCH[root_part[0]]
    for accidental in root_part[1:]:
        if accidental == "#":
            pitch_class += 1
        elif accidental == "b":
            pitch_class -= 1
    return (pitch_class % 12, canonical_quality(quality_part))


def canonical_quality(raw: str) -> str:
    raw = raw.strip()
    if raw in _ALIASES:
        return _ALIASES[raw]
    # Unknown label: resolve to a family so no chord is ever dropped.
    return family_of(raw)


def family_of(quality: str) -> str:
    """Reduce any quality to one of six families.

    Order matters: 'dim' is checked before the minor prefixes so 'hdim7' lands in
    the diminished family, and 'maj' before 'min' so 'minmaj7' reads as minor.
    """
    q = quality.lower()
    if q in ("power", "5"):
        return "power"
    if q.startswith("sus"):
        return "sus"
    if "dim" in q:                                  # dim, dim7, hdim7
        return "diminished"
    if "aug" in q:
        return "augmented"
    if q.startswith("maj"):                         # maj, maj6, maj7
        return "major"
    if q.startswith("min") or q.startswith("m"):    # min, min6, min7, minmaj7, m
        return "minor"
    return "major"


def hue_for(quality: str) -> int:
    if quality in _HUES:
        return _HUES[quality]
    return _FAMILY_HUES[family_of(quality)]
