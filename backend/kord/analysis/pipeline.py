from __future__ import annotations

import shutil
from pathlib import Path

import librosa
import numpy as np

from kord.analysis.beats import BeatTracker
from kord.analysis.key import KeyDetector
from kord.analysis.recognizer import ChordRecognizer
from kord.analysis.timbre import heaviness as measure_heaviness
from kord.audio.decode import SAMPLE_RATE, decode_to_wav, trim_leading_silence
from kord.audio.validate import select_candidate
from kord.models import Analysis, BeatGrid, ChordSegment
from kord.theory.qualities import NO_CHORD


class NoAudioFound(Exception):
    """No candidate passed duration validation."""


class AnalysisPipeline:
    """Fetch, validate, decode, analyze, persist, delete (spec section 6)."""

    def __init__(
        self,
        source,
        recognizer: ChordRecognizer,
        scratch_dir: Path,
        engine_version: str,
        key_detector: KeyDetector | None = None,
        beat_tracker: BeatTracker | None = None,
    ) -> None:
        self.source = source
        self.recognizer = recognizer
        self.scratch_dir = Path(scratch_dir)
        self.engine_version = engine_version
        self.key_detector = key_detector or KeyDetector()
        self.beat_tracker = beat_tracker or BeatTracker()

    def run(
        self, spotify_id: str, artist: str, title: str, spotify_duration_ms: int
    ) -> Analysis:
        candidates = self.source.search(artist, title)
        chosen, tier, ratio = select_candidate(spotify_duration_ms, candidates)
        if chosen is None:
            raise NoAudioFound(f"no candidate matched duration for {artist} - {title}")

        work_dir = self.scratch_dir / spotify_id
        try:
            # The pipeline owns this directory, so it creates it. Sources that
            # return an existing path (local files) never make one, and relying
            # on the source to do it would be a contract waiting to break.
            work_dir.mkdir(parents=True, exist_ok=True)
            downloaded = Path(self.source.download(chosen, work_dir))
            wav_path = decode_to_wav(downloaded, work_dir / "decoded.wav")
            y, sr = librosa.load(wav_path, sr=SAMPLE_RATE, mono=True)
            y, offset_ms = trim_leading_silence(y, sr)

            segments = self.recognizer.recognize(y, sr)
            track_heaviness = measure_heaviness(y, sr)
            key = self.key_detector.detect(y, sr, segments)
            grid = self.beat_tracker.track(y, sr)

            time_scale = ratio if tier == "speed_adjusted" else 1.0
            if time_scale != 1.0:
                segments = [
                    ChordSegment(s.start_s * time_scale, s.end_s * time_scale,
                                 s.root, s.quality, s.confidence)
                    for s in segments
                ]
                grid = BeatGrid(
                    times_s=[t * time_scale for t in grid.times_s],
                    tempo=grid.tempo / time_scale if time_scale else grid.tempo,
                )

            confidences = [s.confidence for s in segments if s.quality != NO_CHORD]
            return Analysis(
                spotify_id=spotify_id,
                engine_version=self.engine_version,
                key=key,
                tempo=grid.tempo,
                beat_grid=grid,
                chord_segments=segments,
                source_url=chosen.url,
                source_duration_ms=chosen.duration_ms,
                time_scale=time_scale,
                sync_offset_ms=offset_ms,
                flags=["speed_adjusted"] if tier == "speed_adjusted" else [],
                chord_confidence_mean=float(np.mean(confidences)) if confidences else 0.0,
                heaviness=track_heaviness,
            )
        finally:
            # Spec: audio is deleted unconditionally, including on failure paths.
            # With 20 GB free, a leak here is what would actually bite.
            shutil.rmtree(work_dir, ignore_errors=True)
