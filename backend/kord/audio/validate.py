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


def rank_candidates(
    spotify_ms: int, candidates: list[AudioCandidate]
) -> list[tuple[AudioCandidate, str, float]]:
    """Every acceptable candidate, best tier first, rejects dropped.

    The duration winner is frequently the official upload, which is DRM
    protected and cannot be downloaded at all. Keeping the runners-up lets the
    pipeline try the next one instead of failing the song outright. Order
    within a tier is the source's own, which is already relevance-ranked.
    """
    clean: list[tuple[AudioCandidate, str, float]] = []
    speed_adjusted: list[tuple[AudioCandidate, str, float]] = []
    for candidate in candidates:
        tier, ratio = classify_ratio(spotify_ms, candidate.duration_ms)
        if tier == "clean":
            clean.append((candidate, tier, ratio))
        elif tier == "speed_adjusted":
            speed_adjusted.append((candidate, tier, ratio))
    return clean + speed_adjusted


def select_candidate(
    spotify_ms: int, candidates: list[AudioCandidate]
) -> tuple[AudioCandidate | None, str, float]:
    """Prefer a clean match; fall back to a speed-adjusted one; else reject."""
    ranked = rank_candidates(spotify_ms, candidates)
    return ranked[0] if ranked else (None, "reject", 0.0)
