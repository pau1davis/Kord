# Kord Phase 4 — note-level tab

**Status:** design, awaiting review
**Date:** 2026-08-17

## 1. What this phase is for

Every phase so far has answered *what chord is this*. This one answers *what
did they actually play* — the notes, on which string, at which fret, moving with
the record.

Phase 3's §9 deferred this and split it in two: chord diagrams (a function of
chord and tuning, tractable) and note-level transcription of a riff
("materially harder than chord recognition and a research-grade problem"). The
warning was put to the user directly, with both options shown, and note-level
tab was chosen with the caveat visible. That choice stands, and this design
takes it seriously rather than quietly building the easy half.

Taking it seriously means the accuracy question is not deferred to the end.
§7 makes measurement the first task, before any interface is built on top.

### Goals

1. Note-level tab for **bass** and **guitar**, generated from separated stems.
2. Tab that is *playable* — positions chosen as a sequence, not note by note.
3. Tab that follows the record, and doubles as the way you navigate it.
4. A measured, published statement of how accurate each instrument's tab is.

### Non-goals

- **Detecting tuning.** Still impossible (Phase 3 §4). The player chooses it.
- **Time signatures.** Nothing detects them; 4/4 is assumed. See §5.3.
- **Articulation** — bends, slides, hammer-ons, vibrato, palm muting. Notes and
  positions only. A tab site marks these by hand; inferring them is a second
  research problem stacked on the first.
- **Drums, vocals, piano.** Tab is for the two instruments the user plays.
- **Editing or correcting the tab.** Read-only output.

## 2. What already exists

| Piece | Where | Status |
|---|---|---|
| Stem separation, 6 parts | `audio/stems.py`, `stem_job` table | done |
| Guitar channel split (double tracking) | `frontend/src/stems.ts` | done |
| Beat grid and tempo | `analysis/beats.py`, `BeatGrid` | done |
| Playhead shared across components | `hooks/usePlayhead.ts` | done |
| Loop ranges | `SongMap`, `chart.ts` | done |
| Reference pitch | `analysis/tuning.py` | done |
| Uncertainty shown, never hidden | chord cards' `uncertain` | precedent to follow |

Transcription depends on stems, which are produced on demand per song. Tab is
therefore only ever available for a song whose parts have been separated, and
the UI must say so rather than appear broken.

## 3. Pipeline

```
stem audio ──▶ note events ──▶ fret positions ──▶ bars ──▶ rendered tab
              (engine-specific)   (pure)          (pure)     (frontend)
```

The note-event format is identical whichever engine produced it, so everything
downstream is engine-agnostic and testable without audio.

### 3.1 Note events

```python
@dataclass(frozen=True)
class NoteEvent:
    start_s: float
    end_s: float
    midi: int
    confidence: float   # 0..1
```

`confidence` means the same thing whichever engine produced it: how much to
trust this note. The two engines do not natively agree on a scale — `pyin`
reports a voiced probability, `basic-pitch` a note-activation strength — so
each adapter is responsible for mapping its own output onto this range. A
number that means one thing for bass and another for guitar would make the
dimming in §5.2 meaningless.

### 3.2 Bass — `pyin`

Already measured working on the separated bass stems (probe, 2026-08-17):
1289 voiced frames on Superdrag's *Wrong vs. Right*, percentiles stable within
a semitone, and the frame count itself flags the sparse cases — Sebadoh's
*Not Too Amused* returned 4 frames, correctly unusable.

`pyin` is monophonic, which is right for bass and wrong for nothing we ask of
it here. It is already a dependency. Per-frame F0 and voiced probability are
segmented into note events by merging frames within a quarter-tone and
splitting on unvoiced gaps.

### 3.3 Guitar — `basic-pitch`

Polyphonic, so it can transcribe a chord voicing and both panned takes.
`basic-pitch` 0.4.0 is on PyPI and needs a runtime (ONNX) alongside it.

This is the unmeasured half. See §7.

### 3.4 Which audio

Bass reads `bass.m4a`. Guitar reads `guitar.m4a`, and when the stem is
double-tracked (L/R correlation ≤ 0.7, per the existing detector) each channel
is transcribed separately and offered as its own part — one guitarist at a
time is what a learner wants, and it is also the easier transcription problem.

## 4. Note events → frets

The interesting problem, and the one that decides whether the output is usable.

E3 can be played in five places on a guitar in standard tuning. Choosing each
note's position independently yields tab that leaps the length of the neck
between consecutive notes: technically correct, unplayable, and worse than
nothing because it looks authoritative.

So position assignment is a **shortest path over the whole sequence**. Each
note contributes a set of candidate `(string, fret)` positions; the cost of a
path is:

- **Hand movement** — distance between consecutive fret positions, dominant term.
- **Stretch** — penalty for spans wider than four frets within a chord or a
  short window.
- **Position** — mild preference for lower frets, where a beginner is.
- **Open strings** — mild bonus; they need no finger.

Dynamic programming over notes × candidate positions. Deterministic, pure, and
entirely testable without audio: given a known sequence of MIDI notes and a
tuning, the assignment is a fixed expected answer.

```python
@dataclass(frozen=True)
class TabNote:
    start_s: float
    end_s: float
    string: int        # 0 = lowest-pitched string
    fret: int
    midi: int
    confidence: float
```

Notes below the lowest open string of the chosen tuning cannot be played at
all. They are dropped and counted, and the count is surfaced — a large number
means the tuning is wrong, which is useful information rather than an error.

## 5. Tuning, bars and layout

### 5.1 Tuning is chosen, not detected

A dropdown, defaulting to E standard for guitar and E-A-D-G for bass, offering
the common alternatives (Eb standard, D standard, Drop D, Drop C, and the bass
equivalents). The measured reference pitch sits beside it, because that *is*
measurable and answers the neighbouring question.

Fret assignment takes tuning as a parameter, so changing it re-renders the same
note events in new positions without re-transcribing. This is what Phase 3's
`string_pitches` was for.

### 5.2 Confidence

Per-note confidence carries through to rendering. Low-confidence notes are
dimmed, following the precedent chord cards already set. Transcription will be
wrong sometimes; the interface says which notes it is unsure of rather than
presenting every note with equal authority.

### 5.3 Bars

Bar lines come from the existing beat grid, four beats to a bar. Nothing in
Kord detects time signature, so 4/4 is assumed and stated in the UI. A song in
3/4 or 6/8 will be barred wrongly while its *notes and positions stay correct*
— the tab is still readable, the bar lines are just in the wrong places.

## 6. Interface

### 6.1 Scrolling is navigation

Decided with the user, and the single most important interaction here:

- Playing: the tab auto-scrolls, current position marked.
- Grab the scrollbar: playback **pauses**. Taking control of the view is an
  interruption, and the record should not keep running away from you.
- Press play: playback resumes **from where you scrolled to**, not from where
  it paused.

The view is scrolled by two things — the playhead and the player — and only one
of them should pause anything. Auto-scroll must therefore be distinguishable
from a human grabbing the bar, or the tab will pause itself the instant it
starts moving. This is the likeliest bug in the whole feature and is called out
here so the plan handles it deliberately rather than discovering it.

So the tab is the transport. Drag to the bar you cannot play, hit play, hear it.
Combined with the loop ranges already in `SongMap`, that is the whole practice
loop without a separate seek control.

### 6.2 Where it lives

Below `PlayAlong`, which already shows the current chord and what is next — the
tab is the same information at note resolution, and belongs directly under it.
An instrument switch (bass / guitar / guitar L / guitar R) selects the part.

### 6.3 When there is nothing to show

Tab needs stems. A song that has not been separated shows the same "Separate
the parts" affordance the mixer uses, not an empty stave.

## 7. Accuracy is measured before it is built on

**This is the first implementation task, and it gates the rest.**

`basic-pitch` on distorted guitar is unmeasured. Distortion is the hard case:
compression flattens dynamics that onset detection relies on, and the added
harmonics look like notes that were never played. Bass is expected to be good;
guitar is the open question.

Method: transcribe the nine separated songs, and score against passages
transcribed by ear. Report per instrument:

- **Note recall** — how many played notes were found.
- **Note precision** — how many reported notes were really played.
- **Pitch accuracy** — of the notes found, how many at the right pitch.
- **Onset timing** — median error in milliseconds.

Thresholds agreed in advance, so the result cannot be rationalised after the
fact:

| Outcome | Action |
|---|---|
| Precision and recall ≥ 0.8 | Build the guitar tab as designed. |
| 0.5–0.8 | Build it, dimmed by confidence, with the measured figures shown in the UI. |
| < 0.5 | **Do not build guitar tab.** Ship bass tab, and report what guitar cannot do. |

The measurement is written up as a note in `docs/notes/` whichever
way it goes, in the manner of the tempo calibration — including the numbers
that argue against the feature.

## 8. Storage

A `tab_job` table mirroring `stem_job` (`spotify_id`, `state`, `error`,
`progress`, timestamps), and note events stored per song and part. Transcription
is slow and never runs on the request path.

Note events are stored, not fret positions: positions depend on the chosen
tuning, and re-deriving them is instant while re-transcribing is not.

## 9. Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/track/{id}/tab` | Start transcription (requires stems). |
| `GET` | `/api/track/{id}/tab` | Status and progress, like the stems endpoint. |
| `GET` | `/api/track/{id}/tab/{part}?tuning=EADGBE` | Fret positions for a part. |

Tuning is a query parameter rather than stored state: it is a property of the
player's instrument at this moment, not of the song.

## 10. Testing

- **Position assignment** — table-driven over known MIDI sequences and tunings.
  Includes the case the whole design exists for: a sequence whose greedy
  per-note assignment leaps the neck, asserted to be assigned in one position.
- **Note segmentation** — synthesised F0 tracks with known note boundaries,
  including unvoiced gaps and a slow bend that must not split into two notes.
- **Bars** — a known beat grid, asserting four beats to a bar and correct
  behaviour when the grid is sparse or absent.
- **Unplayable notes** — a note below the lowest open string is dropped and
  counted, not silently rendered at fret −3.
- **Engines** — measured against real audio (§7), not unit tested. Their output
  format is what the pure layers are tested against.

## 11. Build order

1. **§7 accuracy measurement.** Gates everything else. Nothing is built on
   `basic-pitch` before the numbers exist.
2. Note events and segmentation, both engines, behind one interface.
3. Position assignment and bars — the pure core, fully tested.
4. `tab_job`, storage, endpoints.
5. Rendering, then the scroll-as-transport interaction.

Bass tab is deliverable after 2–5 regardless of what §7 says about guitar.

Step 1 is a spike and produces a note, not code. Steps 2–4 are one
implementation plan; step 5 is a second. One plan covering all five would be
too large to execute or review sensibly, following the Phase 3 convention.

## 12. Open questions

- Whether `basic-pitch` needs ONNX or can share the installed torch. Settled at
  install time in step 1; it changes a dependency line, not the design.
- Whether double-tracked guitars should be transcribed separately or merged.
  §3.4 chooses separately, on the grounds that it is both more useful and
  easier, but the measurement in §7 may show one channel is much cleaner than
  the other and worth preferring.
