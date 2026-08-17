# Transcription accuracy — 2026-08-17

Measuring whether note-level tab can be built honestly, before any interface is
built on it. Thresholds were agreed in the spec (§7) *before* any number here
was seen.

Plan: `docs/plans/2026-08-17-kord-tab-foundations.md`
Spec: `docs/specs/2026-08-17-kord-tab-design.md`

## Install

`basic-pitch[onnx]==0.4.0` resolves on Python 3.11. It pulled
`onnxruntime 1.28.0`, `coremltools 9.0`, `resampy`, `protobuf 7.35.1`.

**It does not actually use ONNX on this machine.** The model path resolves to
`basic_pitch/saved_models/icassp_2022/nmp.mlpackage` — a CoreML package — so
inference runs through coremltools on Apple silicon. The `[onnx]` extra was
still the right thing to install: it is what makes the package resolve without
TensorFlow.

### One dependency conflict, overridden deliberately

`basic-pitch` requires `resampy<0.4.3`. That pin cannot be honoured in this
venv:

- `resampy` 0.4.2 imports `pkg_resources` at module load.
- `setuptools` 84 **removed** `pkg_resources` entirely.

So the pinned version raises `ModuleNotFoundError` on import, and the only way
to satisfy the pin is to hold the whole project below setuptools 81. `resampy`
0.4.3 exists precisely to drop that import; the upper bound is stale rather
than protective. Recorded in `pyproject.toml` under the `tab` extra, with the
reasoning, so it reads as a decision rather than an accident. `pip check` will
report the conflict; that is expected.

### Shape of the output

```
predict(path, ICASSP_2022_MODEL_PATH) -> (model_output, midi, notes)

notes[i] = (start_s: float64, end_s: float64, midi: int64,
            amplitude: float32, bends: list)
```

Amplitude is already `0..1`, which is what the adapter maps onto `confidence`.

### Speed

7.5 seconds for Pantera's *Mouth for War* guitar stem (~3.5 minutes), producing
325 notes. Fast enough to run over every part of a song in a background job
without it being the slow step — stem separation itself takes ~2 minutes.

## Verdict

Pending — see the sections below once Tasks 2 and 3 have run.
