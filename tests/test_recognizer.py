import numpy as np

from kord.analysis.recognizer import ChromaTemplateRecognizer, synth_chord

SR = 22050


def test_recognizes_a_synthesized_c_major_triad():
    y = synth_chord(0, "major", seconds=3.0, sr=SR)
    segments = ChromaTemplateRecognizer().recognize(y, SR)
    dominant = max(segments, key=lambda s: s.duration_s)
    assert dominant.root == 0
    assert dominant.quality == "major"


def test_recognizes_a_synthesized_a_minor_triad():
    y = synth_chord(9, "minor", seconds=3.0, sr=SR)
    segments = ChromaTemplateRecognizer().recognize(y, SR)
    dominant = max(segments, key=lambda s: s.duration_s)
    assert dominant.root == 9
    assert dominant.quality == "minor"


def test_detects_a_change_between_two_chords():
    y = np.concatenate([synth_chord(0, "major", 2.0, SR), synth_chord(7, "major", 2.0, SR)])
    segments = [s for s in ChromaTemplateRecognizer().recognize(y, SR) if s.quality != "none"]
    roots = [s.root for s in segments]
    assert 0 in roots and 7 in roots


def test_silence_yields_no_chord():
    segments = ChromaTemplateRecognizer().recognize(np.zeros(SR * 2, dtype=np.float32), SR)
    assert all(s.quality == "none" for s in segments)


def test_segments_are_contiguous_and_ordered():
    y = np.concatenate([synth_chord(0, "major", 2.0, SR), synth_chord(5, "major", 2.0, SR)])
    segments = ChromaTemplateRecognizer().recognize(y, SR)
    for earlier, later in zip(segments, segments[1:]):
        assert earlier.end_s <= later.start_s + 1e-6
        assert earlier.start_s < earlier.end_s


def test_reports_the_engine_version_used_for_cache_keying():
    assert ChromaTemplateRecognizer().engine_version == "chroma-1"


def test_confidence_is_bounded():
    y = synth_chord(0, "major", 2.0, SR)
    for segment in ChromaTemplateRecognizer().recognize(y, SR):
        assert 0.0 <= segment.confidence <= 1.0
