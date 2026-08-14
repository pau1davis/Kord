"""The ONLY module permitted to import demucs.

Mirrors the AudioSource seam in youtube.py: the dependency sits behind one
file so it can be swapped or removed without touching anything above it.
"""
from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

from typing import Callable

STEM_NAMES: tuple[str, ...] = (
    "drums", "bass", "other", "vocals", "guitar", "piano")

MODEL_NAME = "htdemucs_6s"

# CPU, deliberately. Measured on this machine: 20s of audio takes 10.1s on CPU
# against 11.5s on MPS, so MPS is slower AND carries known instability. Pinning
# CPU removes a fallback path that would otherwise need maintaining.
DEVICE = "cpu"

# Separation is the slow part and the encode is not, so the split reserves most
# of the bar for the model. Measured: ~85s of model against ~12s of ffmpeg for
# a three-minute song.
MODEL_SHARE = 0.88


def encode_stem(samples: np.ndarray, sr: int, dest: Path) -> Path:
    """Write `(channels, samples)` float audio to m4a via ffmpeg."""
    if not np.all(np.isfinite(samples)):
        raise ValueError(f"stem signal is not finite: {dest.name}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    wav = dest.with_suffix(".tmp.wav")
    sf.write(wav, samples.T, sr)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
             "-c:a", "aac", "-b:a", "128k", str(dest)],
            check=True,
        )
    finally:
        wav.unlink(missing_ok=True)
    return dest


class DemucsSeparator:
    """Splits a song into `STEM_NAMES`, written as m4a into `dest_dir`."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):
        # Imported lazily: loading torch and the weights costs seconds, and a
        # process that never separates anything should not pay it.
        if self._model is None:
            from demucs.pretrained import get_model

            self._model = get_model(self.model_name)
        return self._model

    def separate(
        self, source: Path, dest_dir: Path,
        on_progress: "Callable[[float], None] | None" = None,
    ) -> dict[str, Path]:
        import librosa
        import torch
        from demucs.apply import apply_model

        model = self._load()
        y, _ = librosa.load(source, sr=model.samplerate, mono=False)
        if y.ndim == 1:
            y = np.stack([y, y])

        wav = torch.from_numpy(y).float()
        samples = wav.shape[-1]

        def report(data: dict) -> None:
            if on_progress is None or not samples:
                return
            # demucs reports how far into the mix each finished chunk started.
            done = min(1.0, data.get("segment_offset", 0) / samples)
            on_progress(done * MODEL_SHARE)

        out = apply_model(
            model, wav[None], device=DEVICE, progress=False,
            callback=report, callback_arg={"audio_length": samples},
        )[0]

        # ffmpeg is a subprocess, so threads genuinely overlap here rather than
        # queueing behind the GIL. Six sequential encodes were ~12s of the wait.
        pairs = list(zip(model.sources, out))
        with ThreadPoolExecutor(max_workers=min(6, len(pairs))) as pool:
            paths = list(pool.map(
                lambda pair: encode_stem(
                    pair[1].cpu().numpy(), model.samplerate,
                    dest_dir / f"{pair[0]}.m4a"),
                pairs))

        if on_progress is not None:
            on_progress(1.0)
        return {name: path for (name, _), path in zip(pairs, paths)}
