import pytest

from kord.audio.presence import SILENCE_FLOOR_DB, present_parts


def test_a_silent_stem_is_not_in_the_song():
    # htdemucs_6s emits a piano stem for every song whether or not one played.
    assert present_parts({"guitar": -8.0, "piano": -62.0}) == ["guitar"]


def test_everything_audible_is_kept():
    levels = {"guitar": 0.0, "bass": -1.7, "drums": -2.9, "vocals": -5.8}
    assert present_parts(levels) == ["guitar", "bass", "drums", "vocals"]


def test_the_quietest_real_part_in_the_library_survives():
    """Sebadoh's Not Too Amused: the bass enters late, so it reads -32.4 dB
    over the whole song. It is really there and must not be hidden."""
    assert "bass" in present_parts(
        {"guitar": 0.0, "bass": -32.4, "drums": -7.0, "piano": -47.4})


def test_measured_against_the_loudest_stem_not_an_absolute_level():
    # A quietly mastered song must not lose every part at once.
    quiet = {"guitar": -40.0, "bass": -44.0, "piano": -95.0}
    assert present_parts(quiet) == ["guitar", "bass"]


def test_the_floor_sits_clear_of_anything_real():
    # 7.6 dB of margin below the quietest genuine part in the library.
    assert SILENCE_FLOOR_DB == -40.0
    assert -32.4 - SILENCE_FLOOR_DB > 5


def test_no_stems_is_not_a_crash():
    assert present_parts({}) == []


def test_a_song_of_pure_silence_keeps_its_loudest_stem_rather_than_nothing():
    # All equal means the difference is zero, which clears any floor. Better
    # than an empty mixer for a song that does have audio.
    assert present_parts({"guitar": -99.0, "piano": -99.0}) == ["guitar", "piano"]


def test_a_stem_that_will_not_decode_is_kept_not_hidden(tmp_path):
    """Failing to measure a part is not evidence that the part is absent."""
    from kord.audio.presence import level_db

    broken = tmp_path / "guitar.m4a"
    broken.write_bytes(b"not audio at all")
    assert level_db(broken) == 0.0
