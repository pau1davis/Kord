# Chord engine spike — decision record

**Date:** 2026-08-11
**Timebox:** 90 minutes (used ~25)
**Verdict: PASS on all three measurable criteria. BTC large-vocabulary is the primary engine. Task 10 proceeds.**

---

## Environment

Apple M1, 8 GB RAM, arm64, macOS. Python 3.11.3 in `.venv`.

Installed: `torch 2.13.0`, `librosa 0.11.0`, `numpy 2.4.6`, `pyyaml 6.0.3`, `mir_eval`, `pretty_midi`.
Homebrew: `ffmpeg 8.1.2`, `yt-dlp`, `rubberband`.

## Results

Sample: `spike/btc/test/example.mp3` — "Everything is true" by Monplaisir, **257.2 s (4.29 min)**.
Command: `python test.py --voca True` (large vocabulary).

| Criterion | Target | Measured | Verdict |
|---|---|---|---|
| Installs on arm64 / Python 3.11 | no source-build failures | 3 one-line patches, no build failures | **PASS** |
| 4-minute song runtime | < 90 s | **14.01 s** | **PASS** (~18× realtime) |
| Peak resident memory | < 4 GB | **650 MB** (0.65 GB) | **PASS** |
| Chords correct by ear | recognizable | harmonically coherent; not ear-verified | **Pending user check** |

Runtime and memory both beat the criteria by a wide margin — 6.4× faster than required and using a sixth of the memory budget. Memory headroom is large enough that the worker will not pressure an 8 GB machine.

## Corrections to plan assumptions

Two assumptions in the plan were wrong and are now fixed:

1. **Weights ship inside the repository**, at `test/btc_model.pt` and `test/btc_model_large_voca.pt` (~12 MB each). They are **not** GitHub Release assets. The `gh release download` step in Task 0 Step 2 is unnecessary and has been removed from the plan.
2. **A usable sample is bundled** at `test/example.mp3`, so no audio needed sourcing for the spike.

## Required compatibility patches

The codebase is from 2019 and needs three fixes to run on a current stack. **Kord must not depend on the upstream repo directly** — vendor the needed modules and apply these, or apply them at import time.

| File | Problem | Fix |
|---|---|---|
| `utils/hparams.py:29` | `yaml.load(f)` — PyYAML ≥ 6 requires an explicit Loader | `yaml.safe_load(f)` |
| `utils/transformer_modules.py:30` | `np.float` removed in NumPy ≥ 1.24 | `float` |
| `test.py:39` | weights were saved on CUDA; fails to deserialize on a CPU-only machine | `torch.load(..., map_location=device, weights_only=False)` |

Other `np.float` / `np.int` / `np.bool` uses exist in `utils/chords.py` and `audio_dataset.py` but are **not on the inference path** and need no patching.

## Dependency footprint for Kord

`utils/__init__.py` is empty, so the inference path imports only:

```
test.py → utils.logger (stdlib)
        → btc_model → utils.transformer_modules (torch), utils.hparams (yaml)
        → utils.mir_eval_modules (numpy, librosa, mir_eval, torch)
```

**TensorFlow, pyrubberband, pandas and sortedcontainers are NOT required** — they appear only in training files. `pretty_midi` is used solely by `test.py` for MIDI export, so Kord does not need it either.

Kord's production requirement is therefore: **torch, numpy, librosa, mir_eval, pyyaml.**

## Vocabulary

`idx2voca_chord()` returns **170 labels**: 12 roots × 13 qualities, plus bare major, plus `X` and `N`.

Qualities: `7, aug, dim, dim7, hdim7, maj6, maj7, min, min6, min7, minmaj7, sus2, sus4` (and bare = major).

**This validates the spec §7 family-fallback rule against real output.** Exactly three emitted qualities fall outside the spec's hue table — `maj6`, `min6`, `minmaj7` — which is precisely what the fallback and Task 2's test anticipate. The Task 2 parser handles the observed label forms (`F#:7`, `B:maj7`, `A#:min7`, `A:dim7`, `B:sus2`, bare `F#`, `N`) correctly.

Output format is a standard `.lab` file: `start_seconds end_seconds label` per line.

## Accuracy assessment — and its limit

236 segments over the sample. Chord distribution:

```
45 F#      31 B:maj7    28 B      20 A#:min7   15 G#
13 C#      11 B:maj6     7 A#:min  6 F#:min     6 C#:min
```

In **F# major** these are I, IV, iii, V, and ii, with recurring `G#` major as a secondary dominant (V/V) — a standard pop move. The reading is internally coherent rather than noisy, and the large vocabulary is demonstrably active.

**Limit of this assessment:** coherence was verified structurally, by checking the chords against a single consistent key. It was **not verified by ear**, which is what spec §4 actually requires. That check belongs to the user and is deferred to Task 20's 20-song verification.

## Decision

**Proceed with `BtcChordRecognizer` as the primary engine (Task 10).** `ChromaTemplateRecognizer` (Task 9) is still built as planned — it remains the always-installs fallback and, more importantly, the engine the test suite uses so tests stay fast and network-free.

Set `KORD_ENGINE_VERSION=btc-1` once Task 10 lands.
