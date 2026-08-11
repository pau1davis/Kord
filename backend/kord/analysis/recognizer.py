from __future__ import annotations

from typing import Protocol

import librosa
import numpy as np

from kord.models import ChordSegment
from kord.theory.qualities import NO_CHORD

HOP_LENGTH = 2048


class ChordRecognizer(Protocol):
    engine_version: str

    def recognize(self, y: np.ndarray, sr: int) -> list[ChordSegment]: ...


# Interval sets for the templates the baseline can distinguish.
_TEMPLATES: dict[str, tuple[int, ...]] = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
}


def _template_matrix() -> tuple[np.ndarray, list[tuple[int, str]]]:
    rows, labels = [], []
    for quality, intervals in _TEMPLATES.items():
        for root in range(12):
            vector = np.zeros(12, dtype=np.float32)
            for interval in intervals:
                vector[(root + interval) % 12] = 1.0
            rows.append(vector / np.linalg.norm(vector))
            labels.append((root, quality))
    return np.stack(rows), labels


def synth_chord(root_pc: int, quality: str, seconds: float, sr: int) -> np.ndarray:
    """Additive-synthesis test tone, so tests need no audio fixtures or network."""
    intervals = _TEMPLATES[quality]
    t = np.arange(int(seconds * sr)) / sr
    y = np.zeros_like(t, dtype=np.float32)
    for interval in intervals:
        midi = 48 + root_pc + interval          # C3 upward
        freq = 440.0 * 2 ** ((midi - 69) / 12)
        for harmonic, amplitude in ((1, 1.0), (2, 0.4), (3, 0.2)):
            y += amplitude * np.sin(2 * np.pi * freq * harmonic * t).astype(np.float32)
    return (y / np.max(np.abs(y))).astype(np.float32) * 0.8


class ChromaTemplateRecognizer:
    """Cosine-similarity template matching over CQT chroma.

    Recognizes major and minor triads only. Its purpose is to always install and
    to keep the test suite fast and network-free; BtcChordRecognizer supersedes
    it for accuracy and vocabulary. It also remains the fallback if the deep
    engine is ever unavailable.
    """

    engine_version = "chroma-1"

    def __init__(self, silence_rms: float = 1e-3) -> None:
        self.silence_rms = silence_rms
        self._templates, self._labels = _template_matrix()

    def recognize(self, y: np.ndarray, sr: int) -> list[ChordSegment]:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP_LENGTH)
        rms = librosa.feature.rms(y=y, hop_length=HOP_LENGTH)[0]
        times = librosa.frames_to_time(
            np.arange(chroma.shape[1] + 1), sr=sr, hop_length=HOP_LENGTH)

        frame_labels: list[tuple[int, str, float]] = []
        for index in range(chroma.shape[1]):
            column = chroma[:, index]
            norm = np.linalg.norm(column)
            if norm < 1e-8 or rms[min(index, len(rms) - 1)] < self.silence_rms:
                frame_labels.append((-1, NO_CHORD, 0.0))
                continue
            scores = self._templates @ (column / norm)
            best = int(np.argmax(scores))
            root, quality = self._labels[best]
            frame_labels.append((root, quality, float(np.clip(scores[best], 0.0, 1.0))))

        return self._merge(frame_labels, times)

    @staticmethod
    def _merge(frame_labels, times) -> list[ChordSegment]:
        segments: list[ChordSegment] = []
        if not frame_labels:
            return segments
        start_index = 0
        for index in range(1, len(frame_labels) + 1):
            ended = index == len(frame_labels)
            changed = not ended and frame_labels[index][:2] != frame_labels[start_index][:2]
            if ended or changed:
                root, quality, _ = frame_labels[start_index]
                confidences = [c for _, _, c in frame_labels[start_index:index]]
                segments.append(ChordSegment(
                    start_s=float(times[start_index]),
                    end_s=float(times[index]),
                    root=root,
                    quality=quality,
                    confidence=float(np.mean(confidences)) if confidences else 0.0,
                ))
                start_index = index
        return segments
