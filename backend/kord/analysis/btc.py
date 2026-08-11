"""Deep chord recognition via BTC (ISMIR-19 bi-directional transformer).

The model code is vendored under `vendor/btc/`. Feature extraction and the
vocabulary map are reimplemented here rather than vendored, because upstream's
`utils/mir_eval_modules.py` imports `mir_eval` at module level even though
inference never uses it — reimplementing drops that dependency entirely.

Weights are not in the repository. Fetch them once:

    python -m kord.analysis.btc --fetch-weights

Spike results (2026-08-11): 14.0 s and 650 MB peak for a 4.29-minute song on an
M1. See docs/notes/2026-08-11-chord-engine-spike.md
"""
from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np

from kord.models import ChordSegment
from kord.theory.qualities import parse_label

WEIGHTS_FILENAME = "btc_model_large_voca.pt"
WEIGHTS_URL = (
    "https://github.com/jayg996/BTC-ISMIR19/raw/master/test/btc_model_large_voca.pt"
)

# Transcribed from upstream run_config.yaml with the large-vocabulary overrides
# applied (test.py sets these when --voca True). Held as a dict so Kord needs
# neither pyyaml nor upstream's HParams loader.
BTC_CONFIG: dict[str, dict] = {
    "mp3": {"song_hz": 22050, "inst_len": 10.0, "skip_interval": 5.0},
    "feature": {
        "n_bins": 144, "bins_per_octave": 24, "hop_length": 2048, "large_voca": True,
    },
    "model": {
        "feature_size": 144, "timestep": 108, "num_chords": 170,
        "input_dropout": 0.2, "layer_dropout": 0.2, "attention_dropout": 0.2,
        "relu_dropout": 0.2, "num_layers": 8, "num_heads": 4, "hidden_size": 128,
        "total_key_depth": 128, "total_value_depth": 128, "filter_size": 128,
        "loss": "ce", "probs_out": False,
    },
}

_ROOTS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_QUALITIES = [
    "min", "maj", "dim", "aug", "min6", "maj6", "min7", "minmaj7",
    "maj7", "7", "dim7", "hdim7", "sus2", "sus4",
]


def idx2voca_chord() -> dict[int, str]:
    """The 170-label large vocabulary: 12 roots x 14 qualities, plus X and N.

    Quality index 1 ('maj') renders as a bare root, matching upstream.
    """
    vocab: dict[int, str] = {169: "N", 168: "X"}
    for index in range(168):
        root = _ROOTS[index // 14]
        quality_index = index % 14
        vocab[index] = root if quality_index == 1 else f"{root}:{_QUALITIES[quality_index]}"
    return vocab


def labels_to_segments(
    labels: list[tuple[str, float, float, float]]
) -> list[ChordSegment]:
    """Translate (label, start_s, end_s, confidence) tuples, merging repeats."""
    segments: list[ChordSegment] = []
    for label, start_s, end_s, confidence in labels:
        root, quality = parse_label(label)
        if segments and segments[-1].root == root and segments[-1].quality == quality:
            previous = segments[-1]
            segments[-1] = ChordSegment(
                previous.start_s, end_s, root, quality,
                (previous.confidence + confidence) / 2)
        else:
            segments.append(ChordSegment(start_s, end_s, root, quality, confidence))
    return segments


def audio_to_features(y: np.ndarray, sr: int) -> tuple[np.ndarray, float]:
    """CQT log-magnitude features in the layout the checkpoint expects.

    Reimplemented from upstream `audio_file_to_features`, which chunks the signal
    into `inst_len`-second windows before the CQT. Returns (features, seconds_per_frame).
    """
    feature_cfg = BTC_CONFIG["feature"]
    window = int(BTC_CONFIG["mp3"]["song_hz"] * BTC_CONFIG["mp3"]["inst_len"])

    chunks: list[np.ndarray] = []
    position = 0
    while position + window < len(y):
        chunks.append(librosa.cqt(
            y=y[position:position + window], sr=sr,
            n_bins=feature_cfg["n_bins"],
            bins_per_octave=feature_cfg["bins_per_octave"],
            hop_length=feature_cfg["hop_length"]))
        position += window
    chunks.append(librosa.cqt(
        y=y[position:], sr=sr,
        n_bins=feature_cfg["n_bins"],
        bins_per_octave=feature_cfg["bins_per_octave"],
        hop_length=feature_cfg["hop_length"]))

    features = np.log(np.abs(np.concatenate(chunks, axis=1)) + 1e-6)
    seconds_per_frame = BTC_CONFIG["mp3"]["inst_len"] / BTC_CONFIG["model"]["timestep"]
    return features, seconds_per_frame


class BtcChordRecognizer:
    engine_version = "btc-1"

    def __init__(self, weights_path: Path) -> None:
        self.weights_path = Path(weights_path)
        self._model = None
        self._mean = None
        self._std = None
        self._vocab = idx2voca_chord()

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import torch

        from kord.analysis.vendor.btc.btc_model import BTC_model

        if not self.weights_path.exists():
            raise FileNotFoundError(
                f"BTC weights not found at {self.weights_path}. Fetch them with:\n"
                f"  python -m kord.analysis.btc --fetch-weights"
            )
        checkpoint = torch.load(
            self.weights_path, map_location="cpu", weights_only=False)
        model = BTC_model(config=BTC_CONFIG["model"])
        model.load_state_dict(checkpoint["model"])
        model.eval()
        self._model = model
        self._mean = checkpoint["mean"]
        self._std = checkpoint["std"]

    def recognize(self, y: np.ndarray, sr: int) -> list[ChordSegment]:
        self._ensure_loaded()
        return labels_to_segments(self._infer(y, sr))

    def _infer(self, y: np.ndarray, sr: int) -> list[tuple[str, float, float, float]]:
        import torch

        features, seconds_per_frame = audio_to_features(y, sr)
        features = ((features.T - self._mean) / self._std)

        timestep = BTC_CONFIG["model"]["timestep"]
        pad = timestep - (features.shape[0] % timestep)
        features = np.pad(features, ((0, pad), (0, 0)), mode="constant")
        instances = features.shape[0] // timestep

        labels: list[tuple[str, float, float, float]] = []
        with torch.no_grad():
            tensor = torch.tensor(features, dtype=torch.float32).unsqueeze(0)
            start_time = 0.0
            previous: int | None = None
            for instance in range(instances):
                chunk = tensor[:, timestep * instance:timestep * (instance + 1), :]
                attended, _ = self._model.self_attn_layers(chunk)
                prediction, _ = self._model.output_layer(attended)
                prediction = prediction.squeeze()
                for step in range(timestep):
                    current = int(prediction[step].item())
                    now = seconds_per_frame * (timestep * instance + step)
                    if previous is None:
                        previous = current
                        continue
                    if current != previous:
                        labels.append((self._vocab[previous], start_time, now, 1.0))
                        start_time = now
                        previous = current
            # Close the final segment, ignoring the zero-padded tail.
            end_time = seconds_per_frame * (features.shape[0] - pad)
            if previous is not None and end_time > start_time:
                labels.append((self._vocab[previous], start_time, end_time, 1.0))
        return labels


def _fetch_weights(destination: Path) -> Path:
    import urllib.request

    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading BTC weights to {destination} ...")
    urllib.request.urlretrieve(WEIGHTS_URL, destination)
    print(f"Done ({destination.stat().st_size / 1e6:.1f} MB)")
    return destination


if __name__ == "__main__":
    import argparse

    from kord.config import Settings

    parser = argparse.ArgumentParser(description="BTC chord recognizer utilities")
    parser.add_argument("--fetch-weights", action="store_true")
    args = parser.parse_args()
    if args.fetch_weights:
        _fetch_weights(Settings.from_env().model_dir / WEIGHTS_FILENAME)
    else:
        parser.print_help()
