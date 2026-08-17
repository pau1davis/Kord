from __future__ import annotations

from kord.audio.title_match import classify_title
from kord.models import AudioCandidate

CLEAN_LOW, CLEAN_HIGH = 0.995, 1.005
ACCEPT_LOW, ACCEPT_HIGH = 0.98, 1.02

# Best first. Duration outranks the title: a clean length match identifies the
# same master, whereas a speed-adjusted one is pitch-shifted whatever the
# uploader called it.
DURATION_ORDER = ("clean", "speed_adjusted")
TITLE_ORDER = ("preferred", "ok", "video")


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
    spotify_ms: int,
    candidates: list[AudioCandidate],
    artist: str = "",
    title: str = "",
) -> list[tuple[AudioCandidate, str, float]]:
    """Every acceptable candidate, best first, rejects dropped.

    Two independent screens: the length has to match the record, and the title
    has to not announce a different recording. Either one alone lets the wrong
    audio through — a live take at the record's tempo passes on length, and a
    plausible title says nothing about which master was uploaded.

    Rejects are dropped rather than demoted. A live or covered version yields
    confidently wrong chords, which is worse than telling the user the song
    could not be found.

    The winner is frequently the official upload, which is DRM protected and
    cannot be downloaded at all. Keeping the runners-up lets the pipeline try
    the next one instead of failing the song outright. Order within a bucket is
    the source's own, which is already relevance-ranked.
    """
    buckets: dict[tuple[int, int], list[tuple[AudioCandidate, str, float]]] = {}
    for candidate in candidates:
        tier, ratio = classify_ratio(spotify_ms, candidate.duration_ms)
        if tier not in DURATION_ORDER:
            continue
        kind = classify_title(
            candidate.title, artist, title, uploader=candidate.uploader)
        if kind not in TITLE_ORDER:
            continue
        key = (DURATION_ORDER.index(tier), TITLE_ORDER.index(kind))
        buckets.setdefault(key, []).append((candidate, tier, ratio))
    return [entry for key in sorted(buckets) for entry in buckets[key]]


def select_candidate(
    spotify_ms: int,
    candidates: list[AudioCandidate],
    artist: str = "",
    title: str = "",
) -> tuple[AudioCandidate | None, str, float]:
    """Prefer a clean match; fall back to a speed-adjusted one; else reject."""
    ranked = rank_candidates(spotify_ms, candidates, artist, title)
    return ranked[0] if ranked else (None, "reject", 0.0)
