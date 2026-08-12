from __future__ import annotations

import librosa
import numpy as np

from kord.models import ChordSegment
from kord.theory.qualities import NO_CHORD

HOP_LENGTH = 2048

# Heaviness calibration, measured 2026-08-12 over a 90 s window at 30 s offset:
#
#   METAL     Slipknot   5.11 / 15.37    Sabbath  4.72 / 17.09
#             SOAD       5.15 / 17.11    Metallica 5.63 / 15.87
#             Pantera    5.00 / 19.04
#   CLEAN     Beatles    5.16 / 18.81    Bill Evans 6.58 / 18.82
#   ACOUSTIC  S&G        7.08 / 18.56    Elliott  7.95 / 20.04
#             Nick Drake 8.00 / 20.30
#
# Crest factor (peak / RMS) is the primary signal because distortion IS clipping,
# and clipping crushes peaks toward the RMS. Spectral contrast is secondary:
# distortion fills the spectral valleys between harmonics.
#
# Known limitation: loudness-war mastering also crushes crest, so the Beatles
# remaster measures almost identically to Pantera. No feature tested separates
# them, which is why heaviness is a continuous score rather than a class — both
# land mid-scale instead of one being confidently wrong.
CREST_HEAVY, CREST_LIGHT = 4.5, 7.5
CONTRAST_HEAVY, CONTRAST_LIGHT = 15.0, 20.5


def _ramp(value: float, heavy: float, light: float) -> float:
    """1.0 at or beyond `heavy`, 0.0 at or beyond `light`, linear between."""
    if light == heavy:
        return 0.0
    return float(min(1.0, max(0.0, (light - value) / (light - heavy))))


def heaviness_from_features(crest: float, contrast: float) -> float:
    """Combine the two measured signals into a 0-1 heaviness score.

    Geometric mean, so a track must look heavy on *both* axes to score high —
    either one alone is too easily faked by mastering or by a bright mix.
    """
    return float(
        (_ramp(crest, CREST_HEAVY, CREST_LIGHT)
         * _ramp(contrast, CONTRAST_HEAVY, CONTRAST_LIGHT)) ** 0.5
    )


def heaviness(y: np.ndarray, sr: int) -> float:
    """How distorted and crushed a recording sounds, from 0 to 1."""
    if not np.any(np.abs(y) > 1e-6):
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(y))))
    if rms <= 1e-9:
        return 0.0
    crest = float(np.max(np.abs(y)) / rms)
    contrast = float(np.median(
        librosa.feature.spectral_contrast(S=np.abs(librosa.stft(y)), sr=sr)))
    return heaviness_from_features(crest, contrast)
