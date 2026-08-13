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
    dur = 8

    def sine_chord(freqs, seconds, sr, amp=0.15):
        # Mellow pure-tone chord: chroma sees the pitch classes, MFCC sees a plain spectrum.
        t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
        wave = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
        return (amp * wave).astype(np.float32)

    def rich_chord(freqs, seconds, sr, amp=0.35, n_harm=10):
        # Bright, louder, harmonic-rich chord at a different root: distinct in both
        # chroma (different pitch classes) and MFCC (different spectral envelope/energy).
        t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
        wave = np.zeros_like(t)
        for f in freqs:
            for k in range(1, n_harm + 1):
                wave += (1.0 / k) * np.sin(2 * np.pi * f * k * t)
        wave /= len(freqs)
        wave = wave / np.max(np.abs(wave))
        return (amp * wave).astype(np.float32)

    # A-B-A-B: alternating chord root and timbre, 8s each. Real transitions at 8/16/24s.
    a = sine_chord([130.81, 164.81, 196.00], dur, sr)   # C3 major triad, mellow sine
    b = rich_chord([185.00, 233.08, 277.18], dur, sr)   # F#3 major triad, bright harmonics
    y = np.concatenate([a, b, a, b])

    sections = detect_sections(y, sr)
    assert len(sections) >= 2
    assert sections[0].start_s == 0.0
    assert abs(sections[-1].end_s - len(y) / sr) < 0.5
    for earlier, later in zip(sections, sections[1:]):
        assert abs(earlier.end_s - later.start_s) < 1e-6, "sections must be contiguous"
        assert earlier.end_s > earlier.start_s

    # A stub that just bisects the song (e.g. [Section(0, d/2, "A"), Section(d/2, d, "B")])
    # would satisfy every assertion above without ever looking at the audio. Pin down that
    # the detector actually found the real A/B transitions, and labelled them consistently.
    boundaries = [s.start_s for s in sections[1:]]
    tolerance = 1.5  # seconds; agglomerative snaps to ~93ms analysis frames, not sample-exact
    for true_edge in (8.0, 16.0, 24.0):
        assert any(abs(b - true_edge) < tolerance for b in boundaries), (
            f"no detected boundary near true transition at {true_edge}s: {boundaries}"
        )

    def label_at(t):
        for s in sections:
            if s.start_s <= t < s.end_s:
                return s.label
        return sections[-1].label

    # Midpoint of each 8s block should carry a label reflecting the A-B-A-B repeat structure.
    block_labels = [label_at(t) for t in (4.0, 12.0, 20.0, 28.0)]
    assert block_labels[0] == block_labels[2], f"A blocks should share a label: {block_labels}"
    assert block_labels[1] == block_labels[3], f"B blocks should share a label: {block_labels}"
    assert block_labels[0] != block_labels[1], f"A and B blocks should differ: {block_labels}"


def test_detect_sections_on_silence_does_not_crash():
    sr = 22050
    sections = detect_sections(np.zeros(sr * 5, dtype=np.float32), sr)
    assert isinstance(sections, list)
