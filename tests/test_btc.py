import pytest

from kord.analysis.btc import BTC_CONFIG, idx2voca_chord, labels_to_segments


def test_translates_btc_labels_into_segments():
    segments = labels_to_segments([("C:maj", 0.0, 2.0, 0.9), ("A:min", 2.0, 4.0, 0.8)])
    assert (segments[0].root, segments[0].quality) == (0, "major")
    assert (segments[1].root, segments[1].quality) == (9, "minor")


def test_no_chord_labels_become_none_quality():
    segments = labels_to_segments([("N", 0.0, 1.0, 0.5)])
    assert segments[0].quality == "none"
    assert segments[0].root == -1


def test_large_vocabulary_labels_survive_translation():
    segments = labels_to_segments([("F#:hdim7", 0.0, 1.0, 0.7), ("Bb:7", 1.0, 2.0, 0.7)])
    assert (segments[0].root, segments[0].quality) == (6, "hdim7")
    assert (segments[1].root, segments[1].quality) == (10, "dominant7")


def test_adjacent_identical_labels_merge():
    segments = labels_to_segments([("C:maj", 0.0, 1.0, 0.9), ("C:maj", 1.0, 2.0, 0.7)])
    assert len(segments) == 1
    assert segments[0].end_s == 2.0
    assert segments[0].confidence == pytest.approx(0.8)


def test_adjacent_labels_collapsing_to_one_family_are_merged():
    """Observed on real output: BTC emits a 0.09s 'C#:maj6' then 'C#'.

    Both collapse to the major family, so they are one chord as far as the chart
    and the mood ring are concerned, and must not render as two.
    """
    segments = labels_to_segments([
        ("C#:maj6", 35.741, 35.833, 0.9), ("C#", 35.833, 37.130, 0.9)])
    assert len(segments) == 1
    assert (segments[0].root, segments[0].quality) == (1, "major")
    assert segments[0].start_s == 35.741
    assert segments[0].end_s == 37.130


def test_vocabulary_has_the_170_entries_the_spike_measured():
    vocab = idx2voca_chord()
    assert len(vocab) == 170
    assert vocab[169] == "N"
    assert vocab[168] == "X"
    assert vocab[0] == "C:min"
    assert vocab[1] == "C"          # index 1 of each root is bare major


def test_every_vocabulary_entry_parses_to_a_known_quality():
    """Guards the seam between BTC's labels and Kord's theory layer."""
    from kord.theory.qualities import hue_for, parse_label
    for label in idx2voca_chord().values():
        root, quality = parse_label(label)
        if label not in ("N", "X"):
            assert 0 <= root <= 11, label
        assert isinstance(hue_for(quality), int)


def test_config_matches_the_large_vocabulary_checkpoint():
    assert BTC_CONFIG["model"]["num_chords"] == 170
    assert BTC_CONFIG["model"]["timestep"] == 108
    assert BTC_CONFIG["model"]["feature_size"] == 144
    assert BTC_CONFIG["feature"]["n_bins"] == 144
    assert BTC_CONFIG["mp3"]["song_hz"] == 22050
