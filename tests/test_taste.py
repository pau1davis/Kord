from kord.models import Analysis, BeatGrid, ChordSegment, KeyEstimate
from kord.theory.taste import aggregate_palette


def analysis(segments, flags=None, heaviness=0.0, spotify_id="t1"):
    return Analysis(
        spotify_id=spotify_id, engine_version="btc-4",
        key=KeyEstimate(0, "major", 0.9, True), tempo=100.0,
        beat_grid=BeatGrid([0.0], 100.0), chord_segments=segments,
        source_url="u", source_duration_ms=1000, time_scale=1.0,
        sync_offset_ms=0, flags=flags or [], chord_confidence_mean=0.9,
        heaviness=heaviness)


def test_no_analyses_is_an_empty_palette():
    assert aggregate_palette([]) == []


def test_combines_segments_across_songs():
    a = analysis([ChordSegment(0.0, 10.0, 0, "major", 0.9)])
    b = analysis([ChordSegment(0.0, 10.0, 9, "minor", 0.9)], spotify_id="t2")
    stops = aggregate_palette([a, b])
    assert len(stops) == 2
    assert sum(s.weight for s in stops) > 0


def test_a_longer_song_pulls_the_colour_further():
    """Weight is time, so a minute of minor outweighs five seconds of major."""
    a = analysis([ChordSegment(0.0, 60.0, 9, "minor", 0.9)])
    b = analysis([ChordSegment(0.0, 5.0, 0, "major", 0.9)], spotify_id="t2")
    stops = {s.hue: s.weight for s in aggregate_palette([a, b])}
    minor_hue, major_hue = 220, 40
    assert stops[minor_hue] > stops[major_hue]


def test_speed_adjusted_songs_are_excluded():
    """A sped-up upload is pitch-shifted, so its key and colour are unreliable."""
    good = analysis([ChordSegment(0.0, 10.0, 0, "major", 0.9)])
    bad = analysis([ChordSegment(0.0, 99.0, 9, "minor", 0.9)],
                   flags=["speed_adjusted"], spotify_id="t2")
    hues = {s.hue for s in aggregate_palette([good, bad])}
    assert hues == {40}
