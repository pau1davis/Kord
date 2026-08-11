from __future__ import annotations

import librosa
import numpy as np

from kord.models import ChordSegment
from kord.theory.qualities import NO_CHORD

HOP_LENGTH = 2048
THIRD_RATIO_THRESHOLD = 0.35
FLATNESS_THRESHOLD = 0.15


def is_power_chord(
    chroma_mean: np.ndarray,
    root_pc: int,
    flatness: float,
    third_ratio_threshold: float = THIRD_RATIO_THRESHOLD,
    flatness_threshold: float = FLATNESS_THRESHOLD,
) -> bool:
    """A power chord is a root and fifth with no third, played dirty.

    Chord recognizers cannot emit this class: a distorted E5 gets labelled E
    major or E minor, and metal usually sits in a minor key anyway — so without
    this, metal and sad acoustic music both render blue (spec section 7.1).

    Both conditions are required. A clean open fifth is not the heaviness signal
    the mood ring colors red.
    """
    if root_pc < 0:
        return False
    root = float(chroma_mean[root_pc % 12])
    fifth = float(chroma_mean[(root_pc + 7) % 12])
    anchor = (root + fifth) / 2.0
    if anchor <= 1e-6:
        return False
    major_third = float(chroma_mean[(root_pc + 4) % 12])
    minor_third = float(chroma_mean[(root_pc + 3) % 12])
    third_is_absent = (max(major_third, minor_third) / anchor) < third_ratio_threshold
    return third_is_absent and flatness > flatness_threshold


class TimbreProfiler:
    """Reclassifies segments as `power` where the third is absent and the tone is dirty."""

    def __init__(
        self,
        third_ratio_threshold: float = THIRD_RATIO_THRESHOLD,
        flatness_threshold: float = FLATNESS_THRESHOLD,
    ) -> None:
        self.third_ratio_threshold = third_ratio_threshold
        self.flatness_threshold = flatness_threshold

    def profile(
        self, y: np.ndarray, sr: int, segments: list[ChordSegment]
    ) -> list[ChordSegment]:
        if not segments:
            return []

        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP_LENGTH)
        flatness = librosa.feature.spectral_flatness(y=y, hop_length=HOP_LENGTH)[0]
        frame_count = chroma.shape[1]

        result: list[ChordSegment] = []
        for segment in segments:
            if segment.quality == NO_CHORD or segment.root < 0:
                result.append(segment)
                continue
            start = min(int(segment.start_s * sr / HOP_LENGTH), max(frame_count - 1, 0))
            end = max(min(int(segment.end_s * sr / HOP_LENGTH), frame_count), start + 1)
            chroma_mean = chroma[:, start:end].mean(axis=1)
            flatness_mean = float(flatness[start:min(end, len(flatness))].mean())
            if is_power_chord(chroma_mean, segment.root, flatness_mean,
                              self.third_ratio_threshold, self.flatness_threshold):
                result.append(ChordSegment(
                    segment.start_s, segment.end_s, segment.root,
                    "power", segment.confidence))
            else:
                result.append(segment)
        return result
