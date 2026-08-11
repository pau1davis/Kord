from kord.models import ChordSegment, PaletteStop, Analysis, KeyEstimate, BeatGrid


def test_chord_segment_duration():
    seg = ChordSegment(start_s=1.0, end_s=3.5, root=0, quality="major", confidence=0.9)
    assert seg.duration_s == 2.5


def test_chord_segment_rejects_backwards_span():
    import pytest
    with pytest.raises(ValueError):
        ChordSegment(start_s=3.0, end_s=1.0, root=0, quality="major", confidence=0.9)


def test_analysis_roundtrips_through_dict():
    analysis = Analysis(
        spotify_id="abc", engine_version="chroma-1", key=KeyEstimate(0, "major", 0.8, True),
        tempo=120.0, beat_grid=BeatGrid(times_s=[0.0, 0.5], tempo=120.0),
        chord_segments=[ChordSegment(0.0, 2.0, 0, "major", 0.9)],
        source_url="https://example.invalid/x", source_duration_ms=180000,
        time_scale=1.0, sync_offset_ms=0, flags=[], chord_confidence_mean=0.9,
    )
    restored = Analysis.from_dict(analysis.to_dict())
    assert restored.chord_segments[0].quality == "major"
    assert restored.key.mode == "major"
    assert restored.tempo == 120.0
