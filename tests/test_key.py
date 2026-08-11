import numpy as np

from kord.analysis.key import KeyDetector, key_from_chords
from kord.models import ChordSegment

SR = 22050


def test_key_from_a_c_major_chord_progression():
    segments = [
        ChordSegment(0, 2, 0, "major", 0.9),   # C
        ChordSegment(2, 4, 7, "major", 0.9),   # G
        ChordSegment(4, 6, 9, "minor", 0.9),   # Am
        ChordSegment(6, 8, 5, "major", 0.9),   # F
    ]
    assert key_from_chords(segments) == (0, "major")


def test_key_from_a_minor_progression():
    segments = [
        ChordSegment(0, 2, 9, "minor", 0.9),   # Am
        ChordSegment(2, 4, 5, "major", 0.9),   # F
        ChordSegment(4, 6, 0, "major", 0.9),   # C
        ChordSegment(6, 8, 7, "major", 0.9),   # G
    ]
    assert key_from_chords(segments) == (9, "minor")


def test_longer_segments_weigh_more_than_short_ones():
    segments = [
        ChordSegment(0, 60, 6, "major", 0.9),   # F# dominates by duration
        ChordSegment(60, 62, 0, "major", 0.9),
    ]
    root, _ = key_from_chords(segments)
    assert root == 6


def test_empty_segments_return_a_safe_default():
    assert key_from_chords([]) == (0, "major")


def test_no_chord_segments_are_ignored():
    segments = [ChordSegment(0, 100, -1, "none", 0.0),
                ChordSegment(100, 102, 9, "minor", 0.9)]
    assert key_from_chords(segments)[0] == 9


def test_detector_returns_a_key_estimate_with_agreement_flag():
    from kord.analysis.recognizer import synth_chord
    y = np.concatenate([
        synth_chord(0, "major", 2.0, SR), synth_chord(7, "major", 2.0, SR),
        synth_chord(5, "major", 2.0, SR),
    ])
    segments = [ChordSegment(0, 2, 0, "major", 0.9), ChordSegment(2, 4, 7, "major", 0.9),
                ChordSegment(4, 6, 5, "major", 0.9)]
    estimate = KeyDetector().detect(y, SR, segments)
    assert estimate.mode in ("major", "minor")
    assert isinstance(estimate.agreed, bool)
    if estimate.agreed:
        assert estimate.confidence >= 0.7


def test_no_evidence_never_reports_high_confidence():
    """Both estimators default to C major on empty input.

    That is agreement on a fallback, not evidence, and must not be dressed up as
    a confident answer — the UI shows key confidence to the user.
    """
    estimate = KeyDetector().detect(np.zeros(SR, dtype=np.float32), SR, [])
    assert estimate.confidence <= 0.5
    assert estimate.agreed is False


def test_relative_keys_are_separated_by_the_opening_chord():
    """Am-F-C-G and C-G-Am-F use identical notes; only position distinguishes them."""
    a_minor = [ChordSegment(0, 2, 9, "minor", 0.9), ChordSegment(2, 4, 5, "major", 0.9),
               ChordSegment(4, 6, 0, "major", 0.9), ChordSegment(6, 8, 7, "major", 0.9)]
    c_major = [ChordSegment(0, 2, 0, "major", 0.9), ChordSegment(2, 4, 7, "major", 0.9),
               ChordSegment(4, 6, 9, "minor", 0.9), ChordSegment(6, 8, 5, "major", 0.9)]
    assert key_from_chords(a_minor) == (9, "minor")
    assert key_from_chords(c_major) == (0, "major")
