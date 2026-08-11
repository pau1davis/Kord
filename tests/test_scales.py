from kord.theory.scales import note_name, scale_for


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


def test_note_name_prefers_flats_for_black_keys():
    assert note_name(10) == "Bb"
    assert note_name(1) == "Db"


def test_note_name_wraps_octaves():
    assert note_name(12) == "C"
    assert note_name(-1) == "B"
