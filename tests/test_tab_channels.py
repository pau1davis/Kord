import numpy as np
import soundfile as sf

from kord.tab.channels import (
    DOUBLE_TRACKED_MAX_CORR, channel_correlation, split_channels,
)

SR = 22050


def stereo(left, right, path):
    sf.write(path, np.stack([left, right], axis=1).astype(np.float32), SR)
    return path


def tone(freq, seconds=1.0, phase=0.0):
    t = np.arange(int(SR * seconds)) / SR
    return np.sin(2 * np.pi * freq * t + phase)


def test_one_take_panned_centre_reads_as_correlated(tmp_path):
    signal = tone(220.0)
    path = stereo(signal, signal, tmp_path / "mono.wav")
    assert channel_correlation(path) > DOUBLE_TRACKED_MAX_CORR


def test_two_different_takes_read_as_uncorrelated(tmp_path):
    path = stereo(tone(220.0), tone(331.0, phase=1.1), tmp_path / "double.wav")
    assert channel_correlation(path) <= DOUBLE_TRACKED_MAX_CORR


def test_a_mono_file_is_never_double_tracked(tmp_path):
    path = tmp_path / "single.wav"
    sf.write(path, tone(220.0).astype(np.float32), SR)
    assert channel_correlation(path) == 1.0


def test_a_silent_channel_is_not_a_second_guitarist(tmp_path):
    # No variance means no shape to compare. Calling that "uncorrelated" would
    # offer a fader for a performance that does not exist.
    path = stereo(tone(220.0), np.zeros(SR), tmp_path / "half.wav")
    assert channel_correlation(path) == 1.0


def test_a_double_tracked_stem_splits_into_two_named_parts(tmp_path):
    path = stereo(tone(220.0), tone(331.0, phase=1.1), tmp_path / "guitar.wav")
    parts = split_channels(path, tmp_path / "out")
    assert [name for name, _ in parts] == ["guitar (left)", "guitar (right)"]
    assert all(written.exists() for _, written in parts)


def test_a_single_take_stays_one_part(tmp_path):
    signal = tone(220.0)
    path = stereo(signal, signal, tmp_path / "guitar.wav")
    parts = split_channels(path, tmp_path / "out")
    assert [name for name, _ in parts] == ["guitar"]


def test_the_split_channels_are_actually_different_audio(tmp_path):
    # The bug this guards: writing the same channel twice under two names
    # would look right and sound identical.
    path = stereo(tone(220.0), tone(331.0, phase=1.1), tmp_path / "guitar.wav")
    parts = split_channels(path, tmp_path / "out")
    left, _ = sf.read(parts[0][1])
    right, _ = sf.read(parts[1][1])
    assert not np.allclose(left[:1000], right[:1000])


def test_split_parts_are_names_the_store_accepts(tmp_path):
    from kord.tab.store import PARTS

    path = stereo(tone(220.0), tone(331.0, phase=1.1), tmp_path / "guitar.wav")
    for name, _ in split_channels(path, tmp_path / "out"):
        assert name in PARTS
