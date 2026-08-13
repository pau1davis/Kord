import numpy as np

from kord.analysis.sections import detect_sections, label_sections, section_count


def test_section_count_scales_with_duration():
    assert section_count(60) == 4        # clamped floor
    assert section_count(240) == 8       # 240 / 30
    assert section_count(3600) == 12     # clamped ceiling


def test_repeated_features_get_the_same_label():
    verse = np.array([1.0, 0.0, 0.0])
    chorus = np.array([0.0, 1.0, 0.0])
    assert label_sections([verse, chorus, verse, chorus]) == ["A", "B", "A", "B"]


def test_labels_are_assigned_in_order_of_first_appearance():
    a = np.array([1.0, 0.0]); b = np.array([0.0, 1.0])
    assert label_sections([b, a, b]) == ["A", "B", "A"]


def test_distinct_features_get_distinct_labels():
    v = [np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])]
    assert label_sections(v) == ["A", "B", "C"]


def test_near_identical_features_still_share_a_label():
    a = np.array([1.0, 0.05, 0.0])
    b = np.array([0.98, 0.0, 0.02])
    assert label_sections([a, b]) == ["A", "A"]


def test_empty_input_yields_no_labels():
    assert label_sections([]) == []


def test_detect_sections_covers_the_whole_song_without_gaps():
    sr = 22050
    rng = np.random.default_rng(0)
    # A-B-A-B: alternating noise character, 8s each
    a = rng.normal(0, 0.2, sr * 8).astype(np.float32)
    b = (rng.normal(0, 0.2, sr * 8) * np.linspace(1, 3, sr * 8)).astype(np.float32)
    y = np.concatenate([a, b, a, b])

    sections = detect_sections(y, sr)
    assert len(sections) >= 2
    assert sections[0].start_s == 0.0
    assert abs(sections[-1].end_s - len(y) / sr) < 0.5
    for earlier, later in zip(sections, sections[1:]):
        assert abs(earlier.end_s - later.start_s) < 1e-6, "sections must be contiguous"
        assert earlier.end_s > earlier.start_s


def test_detect_sections_on_silence_does_not_crash():
    sr = 22050
    sections = detect_sections(np.zeros(sr * 5, dtype=np.float32), sr)
    assert isinstance(sections, list)
