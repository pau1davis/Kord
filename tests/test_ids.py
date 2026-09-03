import pytest

from kord.metadata.ids import (
    FILE, ITUNES, SPOTIFY, namespaced, native_id_of, provider_of,
)


def test_a_bare_id_is_spotify_forever():
    """The library's 64 tracks, 113 analyses, stems and tab are all keyed on
    bare Spotify IDs. If this ever stops being true they are orphaned."""
    assert provider_of("3VqHuw0wFlIHcIPWkhIbdQ") == SPOTIFY
    assert native_id_of("3VqHuw0wFlIHcIPWkhIbdQ") == "3VqHuw0wFlIHcIPWkhIbdQ"


def test_a_prefixed_id_names_its_provider():
    assert provider_of("itunes:1440857781") == ITUNES
    assert native_id_of("itunes:1440857781") == "1440857781"
    assert provider_of("file:a3f29c81") == FILE


def test_namespaced_builds_what_provider_of_reads():
    for provider, native in ((ITUNES, "1440857781"), (FILE, "a3f2")):
        built = namespaced(provider, native)
        assert provider_of(built) == provider
        assert native_id_of(built) == native


def test_spotify_ids_are_never_given_a_prefix():
    # Prefixing them would create a second ID for a song already in the
    # library, and re-analyse it.
    assert namespaced(SPOTIFY, "3VqHuw0wFlIHcIPWkhIbdQ") == "3VqHuw0wFlIHcIPWkhIbdQ"


def test_an_unknown_prefix_is_refused_rather_than_guessed():
    with pytest.raises(ValueError):
        provider_of("bandcamp:12345")


def test_a_native_id_containing_a_colon_survives_a_round_trip():
    built = namespaced(FILE, "a3f2:9c81")
    assert native_id_of(built) == "a3f2:9c81"


def test_an_empty_id_is_refused():
    with pytest.raises(ValueError):
        provider_of("")


def test_an_explicitly_prefixed_spotify_id_is_malformed():
    """Spotify IDs are written bare, without prefix. If someone passes
    spotify:abc123, that is malformed input, not a second valid spelling."""
    with pytest.raises(ValueError):
        provider_of("spotify:abc123")


def test_native_id_of_rejects_explicitly_prefixed_spotify_ids():
    """native_id_of calls provider_of, so it also rejects the malformed form."""
    with pytest.raises(ValueError):
        native_id_of("spotify:abc123")


def test_round_trip_invariant_for_each_provider():
    """For every non-spotify provider, native_id_of(namespaced(p, n)) == n.
    This is the round-trip invariant the module guarantees."""
    test_cases = [
        (ITUNES, "1440857781"),
        (FILE, "a3f2"),
        (FILE, "a3f2:9c81"),  # native IDs can contain colons
    ]
    for provider, native in test_cases:
        built = namespaced(provider, native)
        assert native_id_of(built) == native, f"round-trip failed for {provider}:{native}"


def test_bare_spotify_ids_survive_unchanged():
    """Existing bare Spotify IDs must stay bare. This is the backward
    compatibility guarantee: the library's 64 tracks never change."""
    spotify_ids = ["3VqHuw0wFlIHcIPWkhIbdQ", "abc123", "0123456789abc"]
    for track_id in spotify_ids:
        assert provider_of(track_id) == SPOTIFY
        assert native_id_of(track_id) == track_id
