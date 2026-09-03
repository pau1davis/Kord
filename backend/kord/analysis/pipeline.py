from __future__ import annotations

import logging
import shutil
from pathlib import Path

import librosa
import numpy as np

from kord.analysis.beats import BeatTracker
from kord.analysis.key import KeyDetector
from kord.analysis.recognizer import ChordRecognizer
from kord.analysis.sections import detect_sections
from kord.analysis.timbre import heaviness as measure_heaviness
from kord.analysis.tuning import estimate_reference
from kord.audio.decode import SAMPLE_RATE, decode_to_wav, trim_leading_silence
from kord.audio.throttle import looks_refused
from kord.audio.validate import rank_candidates
from kord.models import Analysis, Tuning
from kord.theory.qualities import NO_CHORD

log = logging.getLogger("kord.pipeline")


class NoAudioFound(Exception):
    """No candidate passed duration validation, or none could be downloaded."""


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
        audio_store=None,
    ) -> None:
        self.source = source
        self.recognizer = recognizer
        self.scratch_dir = Path(scratch_dir)
        self.engine_version = engine_version
        self.key_detector = key_detector or KeyDetector()
        self.beat_tracker = beat_tracker or BeatTracker()
        self.audio_store = audio_store

    def _download_best(self, ranked, work_dir: Path, artist: str, title: str):
        """First candidate that actually downloads, with its tier and ratio.

        A download can fail for reasons no amount of duration matching predicts
        — DRM on official uploads, region blocks, deleted videos — so a failure
        here means "try the next one", not "this song has no audio".
        """
        refusals = 0
        for candidate, tier, ratio in ranked:
            try:
                return candidate, tier, ratio, Path(
                    self.source.download(candidate, work_dir))
            except Exception as error:
                refusals += bool(looks_refused(error))
                log.warning(
                    "could not download %s, trying the next candidate",
                    candidate.url, exc_info=True)

        # A DRM-protected upload and a rate-limited provider both answer 403,
        # and one attempt cannot tell them apart. The pattern can: a refusal
        # that lets the next candidate through was about that video, while
        # every candidate refused is about us. Reported separately because the
        # first means this song has no audio and the second means try later.
        if refusals and refusals == len(ranked):
            raise NoAudioFound(
                f"{artist} - {title} could not be downloaded: the provider is "
                f"refusing requests, so this is worth retrying later")
        raise NoAudioFound(
            f"every candidate for {artist} - {title} could not be downloaded")

    def run(
        self, spotify_id: str, artist: str, title: str, spotify_duration_ms: int,
        audio_path: Path | None = None,
    ) -> Analysis:
        # A colon is legal in a macOS path but is displayed as `/` by Finder
        # and is not portable, so it is stripped from the directory name.
        work_dir = self.scratch_dir / spotify_id.replace(":", "_")
        if audio_path is not None:
            # An imported file was never found, so there is nothing to search
            # for, no candidate to validate and no upload to be mismatched
            # against — time_scale stays 1.0 and no flag applies.
            chosen, tier, ratio = None, "clean", 1.0
            downloaded = Path(audio_path)
            work_dir.mkdir(parents=True, exist_ok=True)
        else:
            candidates = self.source.search(artist, title)
            ranked = rank_candidates(spotify_duration_ms, candidates, artist, title)
            if not ranked:
                raise NoAudioFound(
                    f"no studio recording of {artist} - {title} was found: every "
                    f"result was the wrong length, or a live take, cover or remix")
            # The pipeline owns this directory, so it creates it. Sources that
            # return an existing path (local files) never make one, and relying
            # on the source to do it would be a contract waiting to break.
            work_dir.mkdir(parents=True, exist_ok=True)
            chosen, tier, ratio, downloaded = self._download_best(
                ranked, work_dir, artist, title)

        try:
            wav_path = decode_to_wav(downloaded, work_dir / "decoded.wav")
            y, sr = librosa.load(wav_path, sr=SAMPLE_RATE, mono=True)
            y, offset_ms = trim_leading_silence(y, sr)

            segments = self.recognizer.recognize(y, sr)
            track_heaviness = measure_heaviness(y, sr)
            key = self.key_detector.detect(y, sr, segments)
            grid = self.beat_tracker.track(y, sr)

            # Timestamps are NOT rescaled. The correction existed to line the
            # chart up with Spotify's master; Kord now plays this exact file, so
            # applying it would introduce drift instead of removing it. The
            # speed_adjusted flag stays: a sped-up upload is pitch-shifted, so
            # the detected key remains unreliable.
            time_scale = ratio if tier == "speed_adjusted" else 1.0

            sections = detect_sections(y, sr)
            reference = estimate_reference(y, sr)

            if self.audio_store is not None:
                try:
                    self.audio_store.retain(spotify_id, downloaded)
                except Exception:
                    # Retention is a convenience; analysis must not depend on it.
                    log.warning("could not retain audio for %s", spotify_id, exc_info=True)

            confidences = [s.confidence for s in segments if s.quality != NO_CHORD]
            return Analysis(
                spotify_id=spotify_id,
                engine_version=self.engine_version,
                key=key,
                tempo=grid.tempo,
                beat_grid=grid,
                chord_segments=segments,
                source_url=chosen.url if chosen else str(audio_path),
                source_duration_ms=chosen.duration_ms if chosen else spotify_duration_ms,
                time_scale=time_scale,
                sync_offset_ms=offset_ms,
                flags=["speed_adjusted"] if tier == "speed_adjusted" else [],
                chord_confidence_mean=float(np.mean(confidences)) if confidences else 0.0,
                heaviness=track_heaviness,
                sections=sections,
                tuning=Tuning(reference_cents=reference.cents,
                              agreement=reference.agreement),
            )
        finally:
            # Spec: audio is deleted unconditionally, including on failure paths.
            # With 20 GB free, a leak here is what would actually bite.
            shutil.rmtree(work_dir, ignore_errors=True)
