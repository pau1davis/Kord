import numpy as np

from kord.analysis.tuning import (
    ReferencePitch, circular_average, estimate_reference,
)


def tone(freq, seconds=4.0, sr=22050):
    """A note with harmonics — estimate_tuning works off spectral peaks."""
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    y = sum(np.sin(2 * np.pi * freq * h * t) / h for h in (1, 2, 3, 4))
    return (y / np.abs(y).max()).astype(np.float32), sr


def test_circular_average_of_a_tight_cluster_is_its_centre():
    fraction, agreement = circular_average([0.06, 0.07, 0.06, 0.07, 0.04])
    assert abs(fraction - 0.06) < 0.01
    assert agreement > 0.99


def test_values_straddling_the_wraparound_are_one_value_not_a_spread():
    """The Mouth for War case, in cents: 49, 49, 48, 47, -43, -50, 42.

    A plain mean answers +20 — a pitch none of the windows reported — and calls
    the spread 99 cents. They are all within about 15 cents of each other.
    """
    windows = [0.49, 0.49, 0.48, 0.47, -0.43, -0.50, 0.42]
    fraction, agreement = circular_average(windows)
    assert abs(abs(fraction) - 0.5) < 0.06, fraction
    assert agreement > 0.9
    assert abs(np.mean(windows) - fraction) > 0.25  # the mean really is wrong


def test_scattered_windows_report_low_agreement():
    _, agreement = circular_average([-0.4, -0.1, 0.0, 0.2, 0.45])
    assert agreement < 0.5


def test_opposite_values_do_not_pretend_to_average():
    fraction, agreement = circular_average([-0.25, 0.25])
    assert agreement < 0.1
    assert -0.5 <= fraction < 0.5


def test_empty_input_is_not_a_crash():
    assert circular_average([]) == (0.0, 0.0)


def test_a_tone_at_concert_pitch_reads_about_zero():
    y, sr = tone(440.0)
    ref = estimate_reference(y, sr, window_s=1.0)
    assert abs(ref.cents) < 8, ref


def test_a_tone_tuned_flat_reads_flat_by_that_much():
    # 30 cents flat of A440.
    y, sr = tone(440.0 * 2 ** (-30 / 1200))
    ref = estimate_reference(y, sr, window_s=1.0)
    assert -40 < ref.cents < -20, ref


def test_a_quarter_step_flat_record_is_not_reported_as_sharp_by_a_hair():
    """A quarter step down lands exactly on the wraparound, which is where a
    naive average flips the sign and a naive spread explodes."""
    y, sr = tone(440.0 * 2 ** (-49 / 1200))
    ref = estimate_reference(y, sr, window_s=1.0)
    assert abs(abs(ref.cents) - 50) < 12, ref
    assert ref.trustworthy


def test_silence_is_reported_as_untrustworthy_rather_than_as_a_number():
    ref = estimate_reference(np.zeros(22050 * 3, dtype=np.float32), 22050,
                             window_s=1.0)
    assert not ref.trustworthy


def test_empty_audio_does_not_crash():
    assert estimate_reference(np.zeros(0, dtype=np.float32), 22050) == \
        ReferencePitch(0.0, 0.0)
