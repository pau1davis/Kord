from kord.theory.scales import note_name, scale_for, uses_sharps


def test_c_major_scale():
    info = scale_for(0, "major")
    assert info.name == "C major"
    assert info.notes == ["C", "D", "E", "F", "G", "A", "B"]


def test_a_minor_scale():
    info = scale_for(9, "minor")
    assert info.name == "A minor"
    assert info.notes == ["A", "B", "C", "D", "E", "F", "G"]


def test_minor_key_suggests_pentatonic_and_relative_major():
    info = scale_for(9, "minor")
    assert "A minor pentatonic" in info.suggestions
    assert "C major" in info.suggestions


def test_major_key_suggests_pentatonic_and_relative_minor():
    info = scale_for(0, "major")
    assert "C major pentatonic" in info.suggestions
    assert "A minor" in info.suggestions


def test_note_name_defaults_to_flats_but_can_use_sharps():
    assert note_name(10) == "Bb"
    assert note_name(1) == "Db"
    assert note_name(6, prefer_sharps=True) == "F#"
    assert note_name(10, prefer_sharps=True) == "A#"


def test_sharp_keys_are_spelled_with_sharps():
    """B major has five sharps; spelling it with flats reads as wrong notation."""
    info = scale_for(11, "major")
    assert info.notes == ["B", "C#", "D#", "E", "F#", "G#", "A#"]
    assert info.name == "B major"


def test_flat_keys_are_spelled_with_flats():
    info = scale_for(3, "major")     # Eb major
    assert info.notes == ["Eb", "F", "G", "Ab", "Bb", "C", "D"]
    assert info.name == "Eb major"


def test_minor_keys_inherit_their_relative_major_spelling():
    assert uses_sharps(4, "minor") is True      # E minor, relative G major
    assert uses_sharps(2, "minor") is False     # D minor, relative F major
    assert scale_for(4, "minor").notes == ["E", "F#", "G", "A", "B", "C", "D"]
    assert scale_for(2, "minor").notes == ["D", "E", "F", "G", "A", "Bb", "C"]


def test_c_major_has_no_accidentals_either_way():
    assert scale_for(0, "major").notes == ["C", "D", "E", "F", "G", "A", "B"]


def test_note_name_wraps_octaves():
    assert note_name(12) == "C"
    assert note_name(-1) == "B"
