from kord.audio.validate import classify_ratio, rank_candidates, select_candidate
from kord.models import AudioCandidate


def cand(duration_ms, url="u"):
    return AudioCandidate(path=None, url=url, duration_ms=duration_ms, title="t")


def test_tier_boundaries_from_spec():
    """Spec section 6 step 2: clean 0.995-1.005, accept 0.98-1.02, else reject."""
    assert classify_ratio(200_000, 200_000)[0] == "clean"           # ratio 1.000000
    assert classify_ratio(200_000, 199_200)[0] == "clean"           # ratio 1.004016
    assert classify_ratio(200_000, 199_000)[0] == "speed_adjusted"  # ratio 1.005025
    assert classify_ratio(200_000, 197_000)[0] == "speed_adjusted"  # ratio 1.015228
    assert classify_ratio(200_000, 195_000)[0] == "reject"          # ratio 1.025641
    assert classify_ratio(200_000, 260_000)[0] == "reject"          # ratio 0.769231


def test_clean_band_is_symmetric_around_unity():
    assert classify_ratio(199_200, 200_000)[0] == "clean"           # ratio 0.996000
    assert classify_ratio(198_900, 200_000)[0] == "speed_adjusted"  # ratio 0.994500


def test_clean_candidate_wins_even_when_listed_later():
    chosen, tier, ratio = select_candidate(
        200_000, [cand(197_000, "speedy"), cand(200_000, "exact")])
    assert chosen.url == "exact"
    assert tier == "clean"
    assert abs(ratio - 1.0) < 1e-9


def test_speed_adjusted_used_only_when_no_clean_option():
    chosen, tier, _ = select_candidate(200_000, [cand(197_000, "speedy")])
    assert chosen.url == "speedy"
    assert tier == "speed_adjusted"


def test_all_rejected_returns_none():
    chosen, tier, _ = select_candidate(200_000, [cand(300_000), cand(90_000)])
    assert chosen is None
    assert tier == "reject"


def test_empty_candidate_list():
    assert select_candidate(200_000, [])[0] is None


def test_zero_duration_candidate_is_rejected_not_crashing():
    assert classify_ratio(200_000, 0)[0] == "reject"


def test_first_speed_adjusted_candidate_wins_over_later_ones():
    chosen, tier, _ = select_candidate(
        200_000, [cand(197_000, "first"), cand(198_000, "second")])
    assert chosen.url == "first"
    assert tier == "speed_adjusted"


def test_rank_orders_clean_before_speed_adjusted_and_drops_rejects():
    ranked = rank_candidates(200_000, [
        cand(300_000, "way too long"),
        cand(197_000, "speedy"),
        cand(200_000, "clean"),
    ])
    assert [c.url for c, _, _ in ranked] == ["clean", "speedy"]
    assert [tier for _, tier, _ in ranked] == ["clean", "speed_adjusted"]


def test_rank_keeps_every_clean_candidate_as_a_fallback():
    """The best duration match can still be undownloadable (DRM), so the
    pipeline needs the runners-up, not just the winner."""
    ranked = rank_candidates(200_000, [cand(200_000, "a"), cand(199_900, "b")])
    assert [c.url for c, _, _ in ranked] == ["a", "b"]


def test_select_candidate_still_returns_the_top_ranked():
    ranked = rank_candidates(200_000, [cand(197_000, "speedy"), cand(200_000, "clean")])
    assert select_candidate(200_000, [cand(197_000, "speedy"), cand(200_000, "clean")]) == ranked[0]
