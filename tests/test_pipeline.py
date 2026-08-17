import tempfile
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


def test_speed_adjusted_candidate_sets_flag_and_records_time_scale(tmp_path):
    # candidate is 1.5% shorter than Spotify: accepted, flagged, time_scale recorded
    analysis = build(tmp_path, FakeSource(tmp_path, 3940)).run("t1", "Artist", "Title", 4000)
    assert "speed_adjusted" in analysis.flags
    assert analysis.time_scale != 1.0


def test_clean_candidate_carries_no_flag(tmp_path):
    analysis = build(tmp_path, FakeSource(tmp_path, 4000)).run("t1", "Artist", "Title", 4000)
    assert analysis.flags == []
    assert analysis.time_scale == pytest.approx(1.0)


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


def test_timestamps_are_never_rescaled(tmp_path):
    """The correction matched Spotify's master. We now play the local file.

    Pink Moon is cached with time_scale=0.992; rescaling against local audio
    drifts about 1.4s over three minutes.
    """
    clean = build(tmp_path, FakeSource(tmp_path, 4000)).run("t1", "A", "T", 4000)
    speedy = build(tmp_path, FakeSource(tmp_path, 3940)).run("t2", "A", "T", 4000)

    assert "speed_adjusted" in speedy.flags, "detection still happens"
    assert speedy.chord_segments[-1].end_s == pytest.approx(
        clean.chord_segments[-1].end_s, rel=1e-6), "but timing is untouched"
    assert speedy.beat_grid.tempo == pytest.approx(clean.beat_grid.tempo, rel=1e-6)


def test_analysis_includes_sections(tmp_path):
    analysis = build(tmp_path, FakeSource(tmp_path, 4000)).run("t1", "A", "T", 4000)
    assert len(analysis.sections) >= 1
    assert analysis.sections[0].label == "A"
    assert analysis.sections[0].start_s == 0.0


def test_audio_is_retained_when_a_store_is_given(tmp_path):
    from kord.audio.store import AudioStore
    store = AudioStore(tmp_path / "store", cap_bytes=10 ** 9)
    pipeline = AnalysisPipeline(
        source=FakeSource(tmp_path, 4000), recognizer=ChromaTemplateRecognizer(),
        scratch_dir=tmp_path / "scratch", engine_version="btc-3", audio_store=store)
    pipeline.run("t1", "A", "T", 4000)
    assert store.path_for("t1") is not None


def test_audio_is_still_deleted_from_scratch_after_retention(tmp_path):
    from kord.audio.store import AudioStore
    store = AudioStore(tmp_path / "store", cap_bytes=10 ** 9)
    source = FakeSource(tmp_path, 4000)
    AnalysisPipeline(source, ChromaTemplateRecognizer(), tmp_path / "scratch",
                     "btc-3", audio_store=store).run("t1", "A", "T", 4000)
    assert not (tmp_path / "scratch" / "t1").exists()


def test_retention_failure_does_not_fail_the_analysis(tmp_path):
    """Analysis must never depend on retention succeeding."""
    class BrokenStore:
        def retain(self, spotify_id, source):
            raise OSError("disk full")

    analysis = AnalysisPipeline(
        FakeSource(tmp_path, 4000), ChromaTemplateRecognizer(),
        tmp_path / "scratch", "btc-3", audio_store=BrokenStore()).run("t1", "A", "T", 4000)
    assert len(analysis.chord_segments) > 0


def test_no_store_means_no_retention_and_still_works(tmp_path):
    analysis = build(tmp_path, FakeSource(tmp_path, 4000)).run("t1", "A", "T", 4000)
    assert len(analysis.chord_segments) > 0


def test_falls_back_to_the_next_candidate_when_a_download_fails(tmp_path):
    """The closest duration match is often the official upload, which is DRM
    protected and 403s. Analysis must move on to the next candidate rather
    than failing the whole song."""
    class FlakySource(FakeSource):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.attempts = []

        def download(self, candidate, dest_dir):
            self.attempts.append(candidate.url)
            if candidate.url.endswith("/drm"):
                raise RuntimeError("HTTP Error 403: Forbidden")
            return super().download(candidate, dest_dir)

    source = FlakySource(tmp_path, 4000, candidates=[
        AudioCandidate(None, "https://example.invalid/drm", 4000, "official"),
        AudioCandidate(None, "https://example.invalid/ok", 4000, "reupload"),
    ])
    analysis = build(tmp_path, source).run("t1", "Artist", "Title", 4000)
    assert source.attempts == ["https://example.invalid/drm", "https://example.invalid/ok"]
    assert analysis.source_url == "https://example.invalid/ok"


def test_raises_when_every_candidate_fails_to_download(tmp_path):
    class DeadSource(FakeSource):
        def download(self, candidate, dest_dir):
            raise RuntimeError("HTTP Error 403: Forbidden")

    source = DeadSource(tmp_path, 4000, candidates=[
        AudioCandidate(None, "https://example.invalid/a", 4000, "a"),
        AudioCandidate(None, "https://example.invalid/b", 4000, "b"),
    ])
    with pytest.raises(NoAudioFound, match="could not be downloaded"):
        build(tmp_path, source).run("t1", "Artist", "Title", 4000)


def test_every_candidate_refused_is_reported_as_worth_retrying():
    """A DRM-protected upload and a rate-limited provider both answer 403, and
    one attempt cannot tell them apart. Every candidate refused is the
    signature of the second: it is about us, not about any of the videos, so
    the song is not hopeless — it is worth another pass later."""
    from kord.analysis.pipeline import AnalysisPipeline, NoAudioFound
    from kord.models import AudioCandidate

    attempts = []

    class RefusingSource:
        def search(self, artist, title):
            return [AudioCandidate(None, f"u{i}", 200_000, "A Song") for i in range(3)]

        def download(self, candidate, dest_dir):
            attempts.append(candidate.url)
            raise RuntimeError("ERROR: unable to download: HTTP Error 403: Forbidden")

    pipeline = AnalysisPipeline(
        source=RefusingSource(), recognizer=None,
        scratch_dir=Path(tempfile.mkdtemp()), engine_version="chroma-1")

    with pytest.raises(NoAudioFound, match="refusing"):
        pipeline.run("t1", "Some Band", "A Song", 200_000)
    assert attempts == ["u0", "u1", "u2"]


def test_an_ordinary_download_failure_still_tries_the_next_candidate():
    """A deleted or private video says nothing about the others."""
    from kord.analysis.pipeline import AnalysisPipeline, NoAudioFound
    from kord.models import AudioCandidate

    attempts = []

    class BrokenSource:
        def search(self, artist, title):
            return [AudioCandidate(None, f"u{i}", 200_000, "A Song") for i in range(3)]

        def download(self, candidate, dest_dir):
            attempts.append(candidate.url)
            raise RuntimeError("ERROR: [youtube] x: This video is not available")

    pipeline = AnalysisPipeline(
        source=BrokenSource(), recognizer=None,
        scratch_dir=Path(tempfile.mkdtemp()), engine_version="chroma-1")

    with pytest.raises(NoAudioFound):
        pipeline.run("t1", "Some Band", "A Song", 200_000)
    assert attempts == ["u0", "u1", "u2"]
