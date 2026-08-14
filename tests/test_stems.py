import numpy as np
import pytest

from kord.audio.stems import STEM_NAMES, encode_stem


def test_stem_names_include_guitar_and_bass():
    """The default htdemucs model folds guitar into 'other'. The whole point of
    using htdemucs_6s is that guitar and bass are separately playable."""
    assert "guitar" in STEM_NAMES
    assert "bass" in STEM_NAMES
    assert len(STEM_NAMES) == 6


def test_encode_stem_writes_a_playable_m4a(tmp_path):
    """WAV would be 254 MB for six stems of a four-minute song; m4a is ~25 MB."""
    sr = 44100
    samples = np.zeros((2, sr), dtype=np.float32)
    samples[0, ::100] = 0.5
    dest = encode_stem(samples, sr, tmp_path / "guitar.m4a")
    assert dest.exists()
    assert dest.suffix == ".m4a"
    assert dest.stat().st_size > 0


def test_encode_stem_rejects_a_non_finite_signal(tmp_path):
    """A NaN reaching the encoder produces a silently corrupt file."""
    samples = np.full((2, 100), np.nan, dtype=np.float32)
    with pytest.raises(ValueError, match="not finite"):
        encode_stem(samples, 44100, tmp_path / "x.m4a")
