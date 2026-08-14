from kord.models import Analysis, BeatGrid, ChordSegment, KeyEstimate
from kord.theory.library import summarise


def analysis(root=0, mode="major", tempo=120.0, spotify_id="t1"):
    return Analysis(
        spotify_id=spotify_id, engine_version="btc-4",
        key=KeyEstimate(root, mode, 0.9, True), tempo=tempo,
        beat_grid=BeatGrid([0.0], tempo),
        chord_segments=[ChordSegment(0.0, 4.0, root, "major", 0.9)],
        source_url="u", source_duration_ms=1000, time_scale=1.0,
        sync_offset_ms=0, flags=[], chord_confidence_mean=0.9)


def test_an_empty_library_reports_nothing_rather_than_zeroes():
    out = summarise([])
    assert out["analyzed"] == 0
    assert out["keys"] == []
    assert out["tempo"] is None


def test_counts_what_has_been_analysed():
    assert summarise([analysis(), analysis(spotify_id="t2")])["analyzed"] == 2


def test_keys_are_ranked_by_how_often_you_play_them():
    out = summarise([analysis(root=4), analysis(root=4), analysis(root=0)])
    assert out["keys"][0]["key"].startswith("E")
    assert out["keys"][0]["count"] == 2


def test_tempo_reports_the_spread_you_actually_play_in():
    out = summarise([analysis(tempo=90.0), analysis(tempo=120.0),
                     analysis(tempo=180.0)])
    assert out["tempo"] == {"min": 90, "median": 120, "max": 180}


def test_a_zero_tempo_is_not_counted_as_the_slowest_song():
    """Silence analyses to tempo 0; it would otherwise anchor the range."""
    out = summarise([analysis(tempo=0.0), analysis(tempo=120.0)])
    assert out["tempo"]["min"] == 120
