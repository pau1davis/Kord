import numpy as np

from kord.audio.decode import trim_leading_silence


def tone(seconds=1.0, sr=22050, freq=440.0):
    t = np.arange(int(seconds * sr)) / sr
    return (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_trims_leading_silence_and_reports_offset_ms():
    sr = 22050
    silence = np.zeros(sr, dtype=np.float32)                     # 1.0s of silence
    trimmed, offset_ms = trim_leading_silence(np.concatenate([silence, tone()]), sr)
    assert 900 <= offset_ms <= 1100
    assert len(trimmed) < len(tone()) + sr


def test_trim_never_clips_the_attack():
    """Boundaries are frame-quantized, so the cut lands just BEFORE the onset.

    That is the safe direction: including a few ms of silence is harmless, while
    clipping the first note of a song is not. Accuracy is +/- one frame.
    """
    sr = 22050
    silence = np.zeros(sr, dtype=np.float32)
    y = np.concatenate([silence, tone()])
    trimmed, _ = trim_leading_silence(y, sr)
    residual_silence = int(np.argmax(np.abs(trimmed) > 1e-6))
    assert residual_silence < 2048          # within one analysis frame
    assert len(trimmed) >= len(tone())      # the whole tone survived, nothing clipped


def test_no_silence_yields_zero_offset():
    sr = 22050
    y = tone()
    trimmed, offset_ms = trim_leading_silence(y, sr)
    assert offset_ms == 0
    assert len(trimmed) == len(y)


def test_all_silence_returns_original_rather_than_empty():
    sr = 22050
    silence = np.zeros(sr, dtype=np.float32)
    trimmed, offset_ms = trim_leading_silence(silence, sr)
    assert len(trimmed) == sr
    assert offset_ms == 0


def test_longer_silence_reports_proportionally_larger_offset():
    sr = 22050
    silence = np.zeros(sr * 3, dtype=np.float32)                 # 3.0s
    _, offset_ms = trim_leading_silence(np.concatenate([silence, tone()]), sr)
    assert 2800 <= offset_ms <= 3200
