import numpy as np


# Measured on real tracks, 2026-08-12 (90s window at 30s offset):
#   METAL     Slipknot 5.11/15.37  Sabbath 4.72/17.09  SOAD 5.15/17.11
#             Metallica 5.63/15.87  Pantera 5.00/19.04
#   CLEAN     Beatles 5.16/18.81   Bill Evans 6.58/18.82
#   ACOUSTIC  S&G 7.08/18.56  Elliott Smith 7.95/20.04  Nick Drake 8.00/20.30
def test_heaviness_scores_metal_high_and_acoustic_at_zero():
    from kord.analysis.timbre import heaviness_from_features

    assert heaviness_from_features(crest=5.11, contrast=15.37) > 0.7   # Slipknot
    assert heaviness_from_features(crest=4.72, contrast=17.09) > 0.7   # Sabbath
    assert heaviness_from_features(crest=5.63, contrast=15.87) > 0.6   # Metallica
    assert heaviness_from_features(crest=7.95, contrast=20.04) == 0.0  # Elliott Smith
    assert heaviness_from_features(crest=8.00, contrast=20.30) == 0.0  # Nick Drake


def test_sparse_acoustic_never_reads_heavy():
    from kord.analysis.timbre import heaviness_from_features
    assert heaviness_from_features(crest=7.08, contrast=18.56) < 0.3   # Simon & Garfunkel
    assert heaviness_from_features(crest=6.58, contrast=18.82) < 0.4   # Bill Evans


def test_loudness_compressed_pop_is_a_known_ambiguity():
    """The Beatles remaster is brick-walled, which measures like clipping.

    No feature tested separates it from Pantera, so both land mid-scale rather
    than one being confidently wrong. Documented, not solved.
    """
    from kord.analysis.timbre import heaviness_from_features
    pantera = heaviness_from_features(crest=5.00, contrast=19.04)
    beatles = heaviness_from_features(crest=5.16, contrast=18.81)
    assert 0.3 < pantera < 0.7
    assert abs(pantera - beatles) < 0.15


def test_heaviness_is_bounded():
    from kord.analysis.timbre import heaviness_from_features
    assert heaviness_from_features(crest=1.0, contrast=1.0) <= 1.0
    assert heaviness_from_features(crest=99.0, contrast=99.0) >= 0.0


def test_heaviness_from_audio_runs_on_real_signal():
    import numpy as np
    from kord.analysis.timbre import heaviness
    sr = 22050
    rng = np.random.default_rng(0)
    clipped = np.clip(rng.normal(0, 1.0, sr * 3).astype(np.float32), -0.3, 0.3)
    score = heaviness(clipped, sr)
    assert 0.0 <= score <= 1.0
