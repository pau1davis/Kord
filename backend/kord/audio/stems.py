"""The ONLY module permitted to import demucs.

Mirrors the AudioSource seam in youtube.py: the dependency sits behind one
file so it can be swapped or removed without touching anything above it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

STEM_NAMES: tuple[str, ...] = (
    "drums", "bass", "other", "vocals", "guitar", "piano")

MODEL_NAME = "htdemucs_6s"

# CPU, deliberately. Measured on this machine: 20s of audio takes 10.1s on CPU
# against 11.5s on MPS, so MPS is slower AND carries known instability. Pinning
# CPU removes a fallback path that would otherwise need maintaining.
DEVICE = "cpu"


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

    def separate(self, source: Path, dest_dir: Path) -> dict[str, Path]:
        import librosa
        import torch
        from demucs.apply import apply_model

        model = self._load()
        y, _ = librosa.load(source, sr=model.samplerate, mono=False)
        if y.ndim == 1:
            y = np.stack([y, y])

        wav = torch.from_numpy(y).float()
        out = apply_model(model, wav[None], device=DEVICE, progress=False)[0]

        written: dict[str, Path] = {}
        for name, tensor in zip(model.sources, out):
            written[name] = encode_stem(
                tensor.cpu().numpy(), model.samplerate, dest_dir / f"{name}.m4a")
        return written
