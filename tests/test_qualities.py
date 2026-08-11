import pytest

from kord.theory.qualities import NO_CHORD, canonical_quality, family_of, hue_for, parse_label


@pytest.mark.parametrize("label,root,quality", [
    ("C:maj", 0, "major"), ("A:min", 9, "minor"), ("F#:hdim7", 6, "hdim7"),
    ("Bb:7", 10, "dominant7"), ("G:sus4", 7, "sus4"), ("E:min7", 4, "minor7"),
    ("C", 0, "major"),
])
def test_parse_label(label, root, quality):
    assert parse_label(label) == (root, quality)


def test_parse_no_chord():
    assert parse_label("N") == (-1, NO_CHORD)
    assert parse_label("X") == (-1, NO_CHORD)


def test_spec_hues_exact():
    # Values fixed by spec section 7 — do not drift
    assert hue_for("power") == 0
    assert hue_for("major") == 40
    assert hue_for("major7") == 40
    assert hue_for("dominant7") == 30
    assert hue_for("sus4") == 170
    assert hue_for("minor") == 220
    assert hue_for("minor7") == 220
    assert hue_for("diminished") == 285
    assert hue_for("hdim7") == 285


def test_unlisted_quality_falls_back_to_family_never_dropped():
    # maj6, min6, minmaj7 are outside the spec table and must still map.
    # The spike confirmed these are exactly the three BTC emits beyond the table.
    assert hue_for(canonical_quality("maj6")) == 40
    assert hue_for(canonical_quality("min6")) == 220
    assert hue_for(canonical_quality("minmaj7")) == 220
    assert hue_for(canonical_quality("totally-unknown")) == 40


def test_family_of():
    assert family_of("minor7") == "minor"
    assert family_of("hdim7") == "diminished"
    assert family_of("power") == "power"


@pytest.mark.parametrize("label", [
    "C:maj", "C:min", "C:7", "C:maj7", "C:min7", "C:maj6", "C:min6", "C:minmaj7",
    "C:dim", "C:dim7", "C:hdim7", "C:aug", "C:sus2", "C:sus4", "C", "N", "X",
])
def test_every_btc_vocabulary_form_parses_and_gets_a_hue(label):
    """The full 170-label BTC vocabulary reduces to these forms (spike, 2026-08-11)."""
    root, quality = parse_label(label)
    if label in ("N", "X"):
        assert (root, quality) == (-1, NO_CHORD)
    else:
        assert root == 0
        assert isinstance(hue_for(quality), int)
