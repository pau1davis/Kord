from kord.models import ChordSegment
from kord.theory.palette import build_palette


def seg(start, end, quality, root=0):
    return ChordSegment(start, end, root, quality, 0.9)


def test_weights_are_duration_proportional_and_normalized():
    stops = build_palette([seg(0, 30, "minor"), seg(30, 40, "major")])
    assert [s.hue for s in stops] == [220, 40]          # sorted by weight desc
    assert stops[0].weight == 0.75
    assert stops[1].weight == 0.25
    assert abs(sum(s.weight for s in stops) - 1.0) < 1e-9


def test_same_hue_from_different_qualities_merges():
    # minor and minor7 both map to 220 and must combine into one stop
    stops = build_palette([seg(0, 10, "minor"), seg(10, 20, "minor7")])
    assert len(stops) == 1
    assert stops[0].hue == 220
    assert stops[0].weight == 1.0


def test_no_chord_segments_are_excluded_from_the_denominator():
    stops = build_palette([seg(0, 10, "major"), seg(10, 90, "none", root=-1)])
    assert len(stops) == 1
    assert stops[0].weight == 1.0


def test_power_chords_dominate_a_metal_track():
    stops = build_palette([seg(0, 70, "power"), seg(70, 100, "minor")])
    assert stops[0].hue == 0
    assert stops[0].weight == 0.7


def test_empty_and_silent_inputs_return_empty():
    assert build_palette([]) == []
    assert build_palette([seg(0, 10, "none", root=-1)]) == []


def test_aggregating_many_songs_uses_the_same_code_path():
    """Phase 3's whole-listening-history ring is the same function over more input."""
    song_a = [seg(0, 100, "power")]
    song_b = [seg(0, 100, "minor")]
    stops = build_palette([*song_a, *song_b])
    assert {s.hue for s in stops} == {0, 220}
    assert all(abs(s.weight - 0.5) < 1e-9 for s in stops)
