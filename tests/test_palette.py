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


HEAVY_HUE = 0


def test_heaviness_blends_red_into_the_palette():
    stops = build_palette([seg(0, 100, "major")], heaviness=0.5)
    hues = {s.hue: s.weight for s in stops}
    assert HEAVY_HUE in hues, "a heavy track must contribute red"
    assert 40 in hues, "the harmony is still represented"
    assert abs(sum(hues.values()) - 1.0) < 1e-9


def test_more_heaviness_means_more_red():
    def red_share(h):
        return next((s.weight for s in build_palette([seg(0, 100, "major")], heaviness=h)
                     if s.hue == HEAVY_HUE), 0.0)

    assert red_share(0.0) == 0.0
    assert red_share(0.47) > 0.2      # Pantera - visibly warm
    assert red_share(0.86) > 0.5      # Slipknot - dominantly red
    assert red_share(0.86) > red_share(0.47) > red_share(0.22)


def test_zero_heaviness_leaves_the_palette_untouched():
    plain = build_palette([seg(0, 70, "minor"), seg(70, 100, "major")])
    same = build_palette([seg(0, 70, "minor"), seg(70, 100, "major")], heaviness=0.0)
    assert plain == same


def test_red_merges_with_power_chords_rather_than_duplicating():
    """Power chords already map to hue 0; heaviness must not create a second stop."""
    stops = build_palette([seg(0, 100, "power")], heaviness=0.5)
    assert len([s for s in stops if s.hue == HEAVY_HUE]) == 1
    assert abs(sum(s.weight for s in stops) - 1.0) < 1e-9


def test_heaviness_on_a_silent_track_stays_empty():
    assert build_palette([], heaviness=0.9) == []
