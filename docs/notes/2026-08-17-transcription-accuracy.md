# Transcription accuracy — 2026-08-17

Measuring whether note-level tab can be built honestly, before any interface is
built on it. Thresholds were agreed in the spec (§7) *before* any number here
was seen.

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

## A. Synthesised material

`synth_accuracy.py` in this directory. Three riffs, each rendered clean and
distorted, with exact per-note truth.

| riff | distorted | true | predicted | precision | recall | pitch | onset | octave err |
|---|---|---|---|---|---|---|---|---|
| single_notes | no | 8 | 24 | 0.29 | 0.88 | 0.47 | 9.4 ms | 0.33 |
| single_notes | **yes** | 8 | 8 | **0.88** | **0.88** | 1.00 | 7.1 ms | 0.00 |
| power_chords | no | 8 | 18 | 0.44 | 1.00 | 0.50 | 11.6 ms | 0.44 |
| power_chords | **yes** | 8 | 12 | **0.67** | **1.00** | 0.67 | 1.9 ms | 0.33 |
| open_chords | no | 11 | 14 | 0.79 | 1.00 | 0.79 | 11.6 ms | 0.21 |
| open_chords | **yes** | 11 | 13 | **0.85** | **1.00** | 0.85 | 11.6 ms | 0.15 |

### Distortion made it *better*, which means the test material is wrong

The spec predicted distortion would be the hard case. It is the easy one here,
on every riff. That is not a discovery about `basic-pitch` — it is a defect in
the synthesis, and it has to be said plainly before any of these numbers are
leaned on.

`render_riff` builds a note as eight harmonics at `1/h` amplitude with an
`exp(-3t)` decay. Two consequences:

1. The clean tone is far brighter than a real clean electric guitar. Its upper
   harmonics are loud enough that the transcriber reports them as notes in
   their own right — hence 24 predictions for 8 true notes, and an octave-error
   rate of 0.33.
2. `tanh` distortion is followed by renormalisation, which acts as heavy
   compression and *sustains* the notes that the sharp decay was cutting short.

So the "distorted" column is not measuring distortion. It is measuring
compression and sustain, which help transcription, against an unrepresentatively
buzzy clean tone, which hurts it. The variable the spec wanted isolated was not
isolated.

**What survives:** recall is high everywhere (0.88–1.00) — the engine finds the
notes that are played. Precision is the weakness, and the dominant failure mode
is the octave error: notes reported an octave from a real one, at rates of 0.15
to 0.44. That pattern is consistent across all six rows and is unlikely to be
an artefact of the synthesis, because it is exactly what a harmonic-rich source
provokes and real guitars are harmonic-rich.

**What does not survive:** the absolute precision figures, in either column.
Source B is therefore doing more work than the spec anticipated.

## B. Chord agreement on the real library

`chord_agreement.py` in this directory. Nine separated songs, every transcribed
guitar note checked for membership of the chord Kord detected at that moment.

| song | notes | foreign | simultaneous octaves |
|---|---|---|---|
| Sebadoh — Not Too Amused | 2481 | 14.3% | 2.5% |
| Superdrag — Cynicality | 1047 | 15.0% | 2.9% |
| John Davis — Tell Me I'm Not Free | 2050 | 17.1% | 2.9% |
| Superdrag — Remain Yer Strange | 1510 | 17.4% | 2.3% |
| Superdrag — Wrong vs. Right | 978 | 18.7% | 1.5% |
| Dinosaur Jr. — Get Me | 4014 | 21.4% | 4.9% |
| Marvin Gaye — Mercy Mercy Me | 1959 | 25.8% | 5.5% |
| **Pantera — Mouth for War** | 319 | **41.1%** | 0.6% |
| **Metallica — Fade To Black** | 3009 | **57.4%** | 3.0% |

Seven of nine land in 14–26%, inside the 15–30% band predicted for competent
transcription of rock guitar. The octave errors that dominated the synthetic
material do not reproduce here at all (0.6–5.5%), which supports the reading
above: that failure was the synthesis, not the engine.

### A hypothesis, tested and rejected

Both outliers are heavily distorted metal, and both records sit far from A440
— so the obvious theory was that a detuned record confuses a transcriber
assuming A440. It does not hold: across the nine songs the correlation between
`|reference_cents|` and the foreign rate is **+0.24**, and Superdrag's *Wrong
vs. Right* sits 33 cents off A440 with a foreign rate of 18.7%. Recorded
because it was checked, not because it explains anything.

### What this measurement cannot tell you

It compares two estimators. Where they disagree, either may be wrong, and
Kord's chord detection is not ground truth. The attempt to check which side was
weak ran into a separate problem — see below — so the outliers stay unexplained.
The likeliest remaining explanation is simply that palm-muted, high-gain power
chords are hard for both, and both songs are full of them. Note also that
*Mouth for War* has only 319 notes against thousands elsewhere, so its rate is
noisy.

## An unrelated bug found on the way

Trying to test whether Kord's chord detection was the weak side of the
disagreement turned up this: **every one of 8,393 chord segments across all
`btc-4` analyses has `confidence` exactly 1.0.**

Consequences, all live in the shipped app:

- `uncertain: segment.confidence < CONFIDENCE_FLOOR` in `app.py` can never be
  true. No chord card has ever been marked uncertain.
- `chord_confidence_mean` carries no information.
- "Uncertainty is shown, never hidden" — a stated project rule and the
  precedent this plan's §5.2 says to follow — does not currently function.

Not fixed here; it belongs to the chord engine, not to tab. But the tab work
should not cite that precedent as though it were working.

## Verdict

**Build guitar tab, dimmed by confidence, with the measured figures shown** —
the spec's middle band (0.5–0.8).

Reasoning, in the order the spec asks for it:

- Source A's distorted rows are 0.88, 0.67 and 0.85 precision with recall 0.88
  to 1.00. Two clear the 0.8 bar; power chords do not. But A's material is
  unrepresentative (above), so this is weak evidence either way.
- Source B is mostly good: seven of nine songs inside the expected band. The
  spec says B wins where the two conflict, and B does not argue against
  building.
- The two sources tell one consistent story about *where* it is weak. Power
  chords score worst on synthetic material, and the two real outliers are the
  two power-chord-heavy metal tracks. That is a specific, statable limitation
  rather than a general unreliability.
- Recall is high everywhere. The engine finds what was played and adds extras,
  and extras are exactly what per-note confidence dimming is for.

So the UI must carry the figures, and must say that high-gain power-chord
material is the weak case. Task 9 proceeds; §5.2's dimming is not optional
decoration here, it is the thing that makes this honest.

Source C — one passage confirmed by the user — is still outstanding and is the
only check on real audio by an ear. Requested separately.
