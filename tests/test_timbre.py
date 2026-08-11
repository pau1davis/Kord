import numpy as np

from kord.analysis.timbre import TimbreProfiler, is_power_chord
from kord.models import ChordSegment


def chroma_with(energies: dict[int, float]) -> np.ndarray:
    vector = np.full(12, 0.02, dtype=np.float32)
    for pitch_class, value in energies.items():
        vector[pitch_class] = value
    return vector


def test_missing_third_plus_distortion_is_a_power_chord():
    # C and G loud, both thirds near-silent, high spectral flatness
    chroma = chroma_with({0: 1.0, 7: 0.9})
    assert is_power_chord(chroma, root_pc=0, flatness=0.30) is True


def test_present_major_third_is_not_a_power_chord_even_when_distorted():
    chroma = chroma_with({0: 1.0, 4: 0.8, 7: 0.9})
    assert is_power_chord(chroma, root_pc=0, flatness=0.30) is False


def test_present_minor_third_is_not_a_power_chord_either():
    chroma = chroma_with({0: 1.0, 3: 0.8, 7: 0.9})
    assert is_power_chord(chroma, root_pc=0, flatness=0.30) is False


def test_missing_third_without_distortion_is_not_a_power_chord():
    # A clean open fifth is not the heaviness signal we want to color red
    chroma = chroma_with({0: 1.0, 7: 0.9})
    assert is_power_chord(chroma, root_pc=0, flatness=0.02) is False


def test_silent_segment_is_not_a_power_chord():
    assert is_power_chord(np.zeros(12, dtype=np.float32), 0, 0.5) is False


def test_no_chord_root_is_not_a_power_chord():
    assert is_power_chord(chroma_with({0: 1.0, 7: 0.9}), -1, 0.5) is False


def test_detection_follows_the_root_not_a_fixed_pitch():
    # Same shape rooted on E (pc 4): E and B loud, thirds absent
    chroma = chroma_with({4: 1.0, 11: 0.9})
    assert is_power_chord(chroma, root_pc=4, flatness=0.30) is True
    assert is_power_chord(chroma, root_pc=0, flatness=0.30) is False


def test_profiler_reclassifies_only_matching_segments():
    sr = 22050
    y = np.random.default_rng(0).normal(0, 0.3, sr * 2).astype(np.float32)  # noisy = flat
    segments = [ChordSegment(0.0, 1.0, 0, "major", 0.9),
                ChordSegment(1.0, 2.0, 7, "minor", 0.9)]
    result = TimbreProfiler().profile(y, sr, segments)
    assert len(result) == 2
    assert all(s.quality in ("major", "minor", "power") for s in result)


def test_profiler_preserves_timings_and_roots():
    sr = 22050
    y = np.random.default_rng(0).normal(0, 0.3, sr * 2).astype(np.float32)
    segments = [ChordSegment(0.0, 1.0, 4, "minor", 0.77)]
    result = TimbreProfiler().profile(y, sr, segments)
    assert result[0].start_s == 0.0
    assert result[0].end_s == 1.0
    assert result[0].root == 4
    assert result[0].confidence == 0.77


def test_profiler_never_touches_no_chord_segments():
    sr = 22050
    y = np.random.default_rng(0).normal(0, 0.3, sr).astype(np.float32)
    segments = [ChordSegment(0.0, 1.0, -1, "none", 0.0)]
    assert TimbreProfiler().profile(y, sr, segments)[0].quality == "none"


def test_profiler_handles_an_empty_segment_list():
    sr = 22050
    y = np.zeros(sr, dtype=np.float32)
    assert TimbreProfiler().profile(y, sr, []) == []
