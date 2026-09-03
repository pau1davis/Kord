"""Which catalogue a track ID came from.

Kord was built against Spotify alone, so every row in `track`, `analysis`,
`job`, `stem_job`, `tab_job` and `tempo_override` is keyed on a bare Spotify
ID. Adding a second provider needs a namespace, and the cheapest one that
cannot break what exists is: no colon means Spotify.

    3VqHuw0wFlIHcIPWkhIbdQ     an existing row, untouched forever
    itunes:1440857781          from the iTunes catalogue
    file:a3f29c81...           an imported file, keyed by content hash

No migration, and this module is the only place that knows the rule.
"""
from __future__ import annotations

SPOTIFY = "spotify"
ITUNES = "itunes"
FILE = "file"

PROVIDERS = (SPOTIFY, ITUNES, FILE)


def provider_of(track_id: str) -> str:
    """Which catalogue this ID belongs to."""
    if not track_id:
        raise ValueError("track id is empty")
    prefix, separator, _rest = track_id.partition(":")
    if not separator:
        return SPOTIFY
    if prefix not in PROVIDERS:
        raise ValueError(f"unknown track id provider: {prefix!r}")
    return prefix


def native_id_of(track_id: str) -> str:
    """The provider's own ID, with any prefix removed."""
    if provider_of(track_id) == SPOTIFY:
        return track_id
    # Split once only: a native ID is free to contain colons of its own.
    return track_id.split(":", 1)[1]


def namespaced(provider: str, native_id: str) -> str:
    """Build a Kord track ID. Spotify IDs are returned bare, so that an
    existing song never acquires a second identity."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider!r}")
    if provider == SPOTIFY:
        return native_id
    return f"{provider}:{native_id}"
