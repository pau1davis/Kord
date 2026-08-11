from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kord.analysis.pipeline import AnalysisPipeline, NoAudioFound
from kord.analysis.recognizer import ChromaTemplateRecognizer, synth_chord
from kord.models import AudioCandidate

SR = 22050


class FakeSource:
    """Writes a real WAV so the pipeline exercises decode and analysis for real."""

    def __init__(self, tmp_path: Path, duration_ms: int, candidates=None):
        self.tmp_path = tmp_path
        self.duration_ms = duration_ms
        self._candidates = candidates
        self.downloaded: list[Path] = []

    def search(self, artist, title):
        if self._candidates is not None:
            return self._candidates
        return [AudioCandidate(None, "https://example.invalid/v", self.duration_ms, "t")]

    def download(self, candidate, dest_dir):
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / "audio.wav"
        y = np.concatenate([synth_chord(0, "major", 2.0, SR), synth_chord(7, "major", 2.0, SR)])
        sf.write(path, y, SR)
        self.downloaded.append(path)
        return path


def build(tmp_path, source):
    return AnalysisPipeline(
        source=source, recognizer=ChromaTemplateRecognizer(),
        scratch_dir=tmp_path / "scratch", engine_version="chroma-1")


def test_produces_an_analysis_with_chords_and_key(tmp_path):
    analysis = build(tmp_path, FakeSource(tmp_path, 4000)).run("t1", "Artist", "Title", 4000)
    assert analysis.spotify_id == "t1"
    assert len(analysis.chord_segments) > 0
    assert analysis.key.mode in ("major", "minor")
    assert analysis.engine_version == "chroma-1"


def test_audio_is_deleted_after_a_successful_run(tmp_path):
    source = FakeSource(tmp_path, 4000)
    build(tmp_path, source).run("t1", "Artist", "Title", 4000)
    assert source.downloaded, "test setup failed to download"
    assert all(not p.exists() for p in source.downloaded)


def test_audio_is_deleted_even_when_analysis_raises(tmp_path):
    class Exploding(ChromaTemplateRecognizer):
        def recognize(self, y, sr):
            raise RuntimeError("engine blew up")

    source = FakeSource(tmp_path, 4000)
    pipeline = AnalysisPipeline(source, Exploding(), tmp_path / "scratch", "chroma-1")
    with pytest.raises(RuntimeError):
        pipeline.run("t1", "Artist", "Title", 4000)
    assert all(not p.exists() for p in source.downloaded)


def test_scratch_directory_is_removed_not_just_the_file(tmp_path):
    source = FakeSource(tmp_path, 4000)
    build(tmp_path, source).run("t1", "Artist", "Title", 4000)
    assert not (tmp_path / "scratch" / "t1").exists()


def test_no_usable_candidate_raises_no_audio_found(tmp_path):
    source = FakeSource(tmp_path, 4000, candidates=[
        AudioCandidate(None, "u", 900_000, "hour long live set")])
    with pytest.raises(NoAudioFound):
        build(tmp_path, source).run("t1", "Artist", "Title", 4000)


def test_empty_candidate_list_raises_no_audio_found(tmp_path):
    source = FakeSource(tmp_path, 4000, candidates=[])
    with pytest.raises(NoAudioFound):
        build(tmp_path, source).run("t1", "Artist", "Title", 4000)


def test_speed_adjusted_candidate_sets_flag_and_scales_timestamps(tmp_path):
    # candidate is 1.5% shorter than Spotify: accepted, corrected, flagged
    analysis = build(tmp_path, FakeSource(tmp_path, 3940)).run("t1", "Artist", "Title", 4000)
    assert "speed_adjusted" in analysis.flags
    assert analysis.time_scale != 1.0


def test_clean_candidate_carries_no_flag(tmp_path):
    analysis = build(tmp_path, FakeSource(tmp_path, 4000)).run("t1", "Artist", "Title", 4000)
    assert analysis.flags == []
    assert analysis.time_scale == pytest.approx(1.0)


def test_time_scale_stretches_segment_boundaries(tmp_path):
    clean = build(tmp_path, FakeSource(tmp_path, 4000)).run("t1", "A", "T", 4000)
    scaled = build(tmp_path, FakeSource(tmp_path, 3940)).run("t2", "A", "T", 4000)
    assert scaled.time_scale > 1.0
    # Same audio, so the final boundary should differ by exactly the scale factor
    assert scaled.chord_segments[-1].end_s == pytest.approx(
        clean.chord_segments[-1].end_s * scaled.time_scale, rel=1e-6)


def test_works_with_a_source_that_does_not_create_the_work_dir(tmp_path):
    """LocalFileAudioSource returns an existing path and never mkdirs.

    The pipeline owns the scratch directory, so it must create it itself rather
    than depending on the source to have done so.
    """
    library = tmp_path / "library"
    library.mkdir()
    audio = library / "Artist - Title.wav"
    sf.write(audio, synth_chord(0, "major", 2.0, SR), SR)

    class NonCreatingSource:
        def search(self, artist, title):
            return [AudioCandidate(str(audio), audio.as_uri(), 2000, audio.name)]

        def download(self, candidate, dest_dir):
            return Path(candidate.path)      # deliberately does not mkdir

    analysis = build(tmp_path, NonCreatingSource()).run("t1", "Artist", "Title", 2000)
    assert len(analysis.chord_segments) > 0


def test_original_source_file_is_not_deleted(tmp_path):
    """Cleanup removes the scratch dir, not the user's own library files."""
    library = tmp_path / "library"
    library.mkdir()
    audio = library / "Artist - Title.wav"
    sf.write(audio, synth_chord(0, "major", 2.0, SR), SR)

    class NonCreatingSource:
        def search(self, artist, title):
            return [AudioCandidate(str(audio), audio.as_uri(), 2000, audio.name)]

        def download(self, candidate, dest_dir):
            return Path(candidate.path)

    build(tmp_path, NonCreatingSource()).run("t1", "Artist", "Title", 2000)
    assert audio.exists(), "cleanup must not delete files outside the scratch dir"


def test_records_the_source_url_and_duration(tmp_path):
    analysis = build(tmp_path, FakeSource(tmp_path, 4000)).run("t1", "Artist", "Title", 4000)
    assert analysis.source_url == "https://example.invalid/v"
    assert analysis.source_duration_ms == 4000
