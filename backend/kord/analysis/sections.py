from __future__ import annotations

import librosa
import numpy as np

from kord.models import Section

HOP_LENGTH = 2048
SECONDS_PER_SECTION = 30
MIN_SECTIONS, MAX_SECTIONS = 4, 12
SIMILARITY_THRESHOLD = 0.85


def section_count(duration_s: float) -> int:
    """One section per ~30s, clamped so short and long songs both stay useful."""
    return int(min(MAX_SECTIONS, max(MIN_SECTIONS, round(duration_s / SECONDS_PER_SECTION))))


def label_sections(
    features: list[np.ndarray], threshold: float = SIMILARITY_THRESHOLD
) -> list[str]:
    """Name repeated sections A, B, C... in order of first appearance.

    Deliberately not "verse"/"chorus": the analysis knows what repeats, not what
    those repeats are called.
    """
    labels: list[str] = []
    exemplars: list[np.ndarray] = []
    for vector in features:
        norm = np.linalg.norm(vector)
        unit = vector / norm if norm > 1e-9 else vector
        match = None
        for index, exemplar in enumerate(exemplars):
            if float(np.dot(unit, exemplar)) >= threshold:
                match = index
                break
        if match is None:
            exemplars.append(unit)
            match = len(exemplars) - 1
        labels.append(chr(ord("A") + match))
    return labels


def detect_sections(y: np.ndarray, sr: int) -> list[Section]:
    """Structural segmentation over stacked chroma and MFCC.

    Chroma catches harmonic change; MFCC catches timbral change, which is what
    separates a quiet verse from a loud chorus when the chords are identical.
    """
    duration_s = len(y) / sr
    if duration_s <= 0 or not np.any(np.abs(y) > 1e-6):
        return []

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP_LENGTH)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=HOP_LENGTH)
    stacked = np.vstack([chroma, mfcc])

    wanted = min(section_count(duration_s), stacked.shape[1])
    if wanted < 2:
        return [Section(0.0, duration_s, "A")]

    bounds = librosa.segment.agglomerative(stacked, wanted)
    times = list(librosa.frames_to_time(bounds, sr=sr, hop_length=HOP_LENGTH))
    edges = [0.0] + [float(t) for t in times if 0.0 < t < duration_s] + [duration_s]
    edges = sorted(set(edges))

    features = []
    for start, end in zip(edges, edges[1:]):
        lo = int(start * sr / HOP_LENGTH)
        hi = max(int(end * sr / HOP_LENGTH), lo + 1)
        features.append(stacked[:, lo:hi].mean(axis=1))

    labels = label_sections(features)
    return [Section(start, end, label)
            for (start, end), label in zip(zip(edges, edges[1:]), labels)]
