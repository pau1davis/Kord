import pytest

from kord.theory.roman import roman_numeral


@pytest.mark.parametrize("chord_root,quality,expected", [
    (0, "major", "I"), (2, "minor", "ii"), (4, "minor", "iii"),
    (5, "major", "IV"), (7, "major", "V"), (9, "minor", "vi"),
    (11, "diminished", "vii°"), (7, "dominant7", "V7"),
])
def test_diatonic_in_c_major(chord_root, quality, expected):
    assert roman_numeral(0, "major", chord_root, quality) == expected


@pytest.mark.parametrize("chord_root,quality,expected", [
    (9, "minor", "i"), (0, "major", "III"), (4, "minor", "v"),
    (2, "minor", "iv"), (7, "major", "VII"),
])
def test_diatonic_in_a_minor(chord_root, quality, expected):
    assert roman_numeral(9, "minor", chord_root, quality) == expected


def test_borrowed_chords_get_accidentals():
    assert roman_numeral(0, "major", 10, "major") == "bVII"   # bVII in C major
    assert roman_numeral(0, "major", 3, "major") == "bIII"


def test_raised_seventh_in_minor_is_sharp_not_flat_one():
    """In A minor the natural VII is G (pc 7). G# (pc 8) is the raised seventh.

    Spelling it by flattening the degree above would wrap to the tonic and yield
    the nonsense "bI", so it must resolve downward to "#VII" instead.
    """
    assert roman_numeral(9, "minor", 7, "major") == "VII"    # G major, diatonic
    assert roman_numeral(9, "minor", 8, "major") == "#VII"   # G# major, raised


def test_non_diatonic_below_the_tonic_still_flattens_normally():
    # Db in A minor is a flattened IV, not a seventh
    assert roman_numeral(9, "minor", 1, "major") == "bIV"


def test_power_chord_has_no_case_implication():
    assert roman_numeral(0, "major", 0, "power") == "I5"


def test_no_chord_returns_empty():
    assert roman_numeral(0, "major", -1, "none") == ""
