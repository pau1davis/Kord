import pytest

from kord.analysis.btc import (
    BTC_CONFIG, frames_to_labels, idx2voca_chord, labels_to_segments,
)


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


def test_decode_frames_reports_the_model_s_own_probability():
    """The bug this fixes: confidence was hardcoded to 1.0 at both places a
    label was emitted, so `uncertain` never fired on any chord ever analysed.

    The probability is right there — the vendored softmax layer computes topk
    and returns only the indices, discarding the values.
    """
    torch = pytest.importorskip("torch")
    from kord.analysis.btc import decode_frames

    # Two frames: the first sure of class 1, the second torn between 0 and 2.
    probs = torch.tensor([[[0.02, 0.95, 0.03],
                           [0.45, 0.11, 0.44]]])
    indices, confidences = decode_frames(probs)
    assert list(indices) == [1, 0]
    assert confidences[0] == pytest.approx(0.95, abs=1e-5)
    assert confidences[1] == pytest.approx(0.45, abs=1e-5)


def test_decode_frames_confidence_stays_a_probability():
    torch = pytest.importorskip("torch")
    from kord.analysis.btc import decode_frames

    probs = torch.rand(1, 16, 170)
    probs = probs / probs.sum(dim=-1, keepdim=True)
    _, confidences = decode_frames(probs)
    assert all(0.0 <= c <= 1.0 for c in confidences)


def test_segment_confidence_is_averaged_across_its_frames():
    """A segment held over frames of mixed certainty reports the average, not
    the best frame — otherwise one confident frame launders a doubtful chord."""
    segments = labels_to_segments([
        ("C:maj", 0.0, 1.0, 0.9), ("C:maj", 1.0, 2.0, 0.3)])
    assert len(segments) == 1
    assert segments[0].confidence == pytest.approx(0.6)


VOCAB = {0: "C", 1: "A:min", 2: "G"}


def test_frames_to_labels_makes_a_span_per_run():
    labels = frames_to_labels(VOCAB, [0, 0, 1, 1, 1], [0.9] * 5, 1.0)
    assert [(l[0], l[1], l[2]) for l in labels] == [
        ("C", 0.0, 2.0), ("A:min", 2.0, 5.0)]


def test_a_span_averages_only_its_own_frames():
    labels = frames_to_labels(VOCAB, [0, 0, 1, 1], [1.0, 0.6, 0.2, 0.4], 1.0)
    assert labels[0][3] == pytest.approx(0.8)
    assert labels[1][3] == pytest.approx(0.3)


def test_a_chord_spanning_a_chunk_boundary_keeps_every_frame():
    """The bug this shape prevents: the model runs in 108-frame chunks, and
    averaging confidence per chunk meant a chord ending on the first frame of a
    new chunk averaged an empty list and reported 0.0 — reading as maximum
    uncertainty about a chord the model was sure of.

    Given every frame at once, a run of 110 cannot be split by a boundary that
    no longer exists here.
    """
    frames = [0] * 110 + [1] * 5
    labels = frames_to_labels(VOCAB, frames, [0.8] * 115, 0.1)
    assert len(labels) == 2
    assert labels[0][3] == pytest.approx(0.8)
    assert labels[1][3] == pytest.approx(0.8)


def test_no_span_is_ever_averaged_over_nothing():
    frames = [0] * 108 + [1] * 108 + [2] * 108
    labels = frames_to_labels(VOCAB, frames, [0.75] * 324, 0.0929)
    assert all(l[3] > 0.0 for l in labels), labels


def test_no_frames_is_not_a_crash():
    assert frames_to_labels(VOCAB, [], [], 1.0) == []
