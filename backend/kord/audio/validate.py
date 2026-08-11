from __future__ import annotations

from kord.models import AudioCandidate

CLEAN_LOW, CLEAN_HIGH = 0.995, 1.005
ACCEPT_LOW, ACCEPT_HIGH = 0.98, 1.02


def classify_ratio(spotify_ms: int, candidate_ms: int) -> tuple[str, float]:
    """Spec section 6 step 2. Returns (tier, ratio).

    Filters live cuts, covers and extended edits, and flags the 1-2% speed-ups
    that YouTube uploaders use to evade Content ID.
    """
    if candidate_ms <= 0:
        return ("reject", 0.0)
    ratio = spotify_ms / candidate_ms
    if CLEAN_LOW <= ratio <= CLEAN_HIGH:
        return ("clean", ratio)
    if ACCEPT_LOW <= ratio <= ACCEPT_HIGH:
        return ("speed_adjusted", ratio)
    return ("reject", ratio)


def select_candidate(
    spotify_ms: int, candidates: list[AudioCandidate]
) -> tuple[AudioCandidate | None, str, float]:
    """Prefer a clean match; fall back to a speed-adjusted one; else reject."""
    fallback: tuple[AudioCandidate, float] | None = None
    for candidate in candidates:
        tier, ratio = classify_ratio(spotify_ms, candidate.duration_ms)
        if tier == "clean":
            return (candidate, "clean", ratio)
        if tier == "speed_adjusted" and fallback is None:
            fallback = (candidate, ratio)
    if fallback is not None:
        return (fallback[0], "speed_adjusted", fallback[1])
    return (None, "reject", 0.0)
