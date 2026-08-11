from __future__ import annotations

from collections import defaultdict

import librosa
import numpy as np

from kord.models import ChordSegment, KeyEstimate
from kord.theory.qualities import NO_CHORD, family_of

# Krumhansl-Schmuckler key profiles.
_MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

_MAJOR_SCALE = {0, 2, 4, 5, 7, 9, 11}
_MINOR_SCALE = {0, 2, 3, 5, 7, 8, 10}


_FIRST_CHORD_BONUS = 1.0
_LAST_CHORD_BONUS = 0.75


def key_from_chords(segments: list[ChordSegment]) -> tuple[int, str]:
    """Score every key by how much chord time is diatonic to it.

    Diatonic membership alone cannot separate relative keys: Am-F-C-G scores
    identically for C major, F major and A minor, because the same seven notes
    serve all three. The tiebreaker is positional — songs tend to open and close
    on the tonic — so the first and last chords get an extra vote for the key
    they would be the tonic of.
    """
    playable = [s for s in segments if s.quality != NO_CHORD and s.root >= 0]
    if not playable:
        return (0, "major")

    scores: dict[tuple[int, str], float] = defaultdict(float)
    for segment in playable:
        weight = segment.duration_s
        for tonic in range(12):
            interval = (segment.root - tonic) % 12
            if interval in _MAJOR_SCALE:
                scores[(tonic, "major")] += weight
                if interval == 0 and family_of(segment.quality) == "major":
                    scores[(tonic, "major")] += weight * 0.5     # tonic bonus
            if interval in _MINOR_SCALE:
                scores[(tonic, "minor")] += weight
                if interval == 0 and family_of(segment.quality) == "minor":
                    scores[(tonic, "minor")] += weight * 0.5

    for segment, bonus in ((playable[0], _FIRST_CHORD_BONUS),
                           (playable[-1], _LAST_CHORD_BONUS)):
        mode = "minor" if family_of(segment.quality) == "minor" else "major"
        scores[(segment.root, mode)] += segment.duration_s * bonus

    return max(scores.items(), key=lambda item: item[1])[0]


def key_from_chroma(y: np.ndarray, sr: int) -> tuple[int, str]:
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    if float(np.sum(chroma)) < 1e-6:
        return (0, "major")
    best, best_score = (0, "major"), -np.inf
    for tonic in range(12):
        rotated = np.roll(chroma, -tonic)
        for mode, profile in (("major", _MAJOR_PROFILE), ("minor", _MINOR_PROFILE)):
            score = float(np.corrcoef(rotated, profile)[0, 1])
            if score > best_score:
                best, best_score = (tonic, mode), score
    return best


class KeyDetector:
    """Two independent estimates. Agreement raises confidence; disagreement lowers it.

    Disagreement is surfaced in the UI rather than hidden — for a tool you learn
    from, visible uncertainty beats a confident lie (spec section 10).
    """

    def detect(self, y: np.ndarray, sr: int, segments: list[ChordSegment]) -> KeyEstimate:
        has_chords = any(s.quality != NO_CHORD and s.root >= 0 for s in segments)
        has_audio = bool(np.any(np.abs(y) > 1e-6))
        from_chroma = key_from_chroma(y, sr)

        if not has_chords:
            # Both estimators fall back to the same default here. Agreeing on a
            # default is not evidence, so this must never report high confidence.
            return KeyEstimate(
                root=from_chroma[0], mode=from_chroma[1],
                confidence=0.35 if has_audio else 0.1,
                agreed=False,
            )

        from_chords = key_from_chords(segments)
        agreed = from_chords == from_chroma
        return KeyEstimate(
            root=from_chords[0], mode=from_chords[1],
            confidence=0.85 if agreed else 0.45,
            agreed=agreed,
        )
