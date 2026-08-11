# Phase 1 verification

**Date:** 2026-08-11
**Status: machine-verifiable checks all pass. The by-ear accuracy gate is outstanding and belongs to the user.**

---

## What was verified

### Test suite

180 tests, all passing, in ~5 seconds. No test touches the network — audio is
synthesised in numpy, so there are no fixture files and no dependency on YouTube
or Spotify being reachable. A test greps the source tree to assert `yt_dlp` is
imported in exactly one file.

### Chord engine, against a reference implementation

Kord's reimplemented BTC inference was compared to the upstream `test.py` run
from the spike, on the same 4.29-minute track:

| | |
|---|---|
| Raw labels emitted | 236 vs 236 |
| Label mismatches | **0** |
| Timestamp drift | < 5 ms |

Bit-for-bit identical, while dropping `mir_eval`, `pretty_midi`, `pyyaml` and
TensorFlow from the dependency tree. Production needs only torch, numpy, librosa.

The 6-segment difference in the *final* output is intentional: adjacent labels
that collapse to the same canonical quality (`C#:maj6` then `C#`) are merged,
since they are one chord as far as the chart and the mood ring are concerned.

### End-to-end run on real audio

Full chain — source → duration validation → decode → recognise → timbre → key →
beats → persist → render:

```
job state : done  (6.4s for a 4.3-minute song)
key       : B major  (uncertain=True)
tempo     : 123.0 BPM
chart     : 241 chords
scale     : B C# D# E F# G# A#
palette   : hue 40 = 71%, hue 220 = 25%, hue 30 = 2%, hue 170 = 2%
sync off  : 882 ms
scratch cleaned    : True
source file intact : True
```

### Running system

| Check | Result |
|---|---|
| `uvicorn kord.app:build_app --factory` | serves |
| `GET /api/health` | `{"status":"ok","engine":"chroma-1"}` |
| `GET /api/search` unauthenticated | 401 |
| `GET /api/auth/login` | 307 to a real Spotify authorize URL with S256 PKCE params |
| Vite dev server | serves; every module compiles (200) |
| `/api/*` proxy through Vite | reaches the backend |
| Frontend build | clean, zero TypeScript errors |
| Backend payload vs `api.ts` types | every required field present, types match, JSON-serialisable |

## Bugs found by running it, not by unit tests

1. **Pipeline never created its scratch directory.** It only passed because the
   test's `FakeSource` happened to `mkdir` it, while `LocalFileAudioSource`
   returns an existing path and does not. ffmpeg failed on a missing directory.
   Fixed, with a regression test using a source that deliberately does not mkdir.

2. **Notes were spelled in flats regardless of key.** B major rendered as
   `B Db Eb E Gb Ab Bb` with chords labelled `Gb` — five sharps written as flats,
   which any guitarist would read as wrong. Now sharp keys use sharps and minor
   keys inherit their relative major's spelling.

3. **No zero-argument app factory.** `create_app` takes injected dependencies for
   testability, so the documented `uvicorn --factory` command could not start the
   server at all. Added `build_app`, with a test asserting its signature stays
   empty because the README depends on it.

Also fixed during the build, found by tests: relative-key ambiguity in key
detection (Am-F-C-G scored identically for C major, F major and A minor), false
high confidence when there was no evidence at all, and an engine-version mismatch
that would have made every cache lookup miss in silence.

## What is NOT verified

**The spec section 4 success criterion is not met yet, because it cannot be met
without the user.** It reads: *"for a personally chosen set of 20 songs across
genres, the chord chart is accurate enough to play along with by ear, and the
mood ring visibly distinguishes heavy songs from sad ones."*

Two parts are outstanding:

1. **Chord accuracy by ear.** Verified structurally — the chords form a coherent
   reading in a single key, and match a reference implementation exactly — but
   never listened to. Whether the charts are good enough to play along with is a
   judgement only the user can make.

2. **The mood ring's red.** No distorted, power-chord-driven track has been run
   through the pipeline yet. The sample was an upbeat major-key instrumental,
   which correctly rendered 71% gold. **The power-chord detector has never fired
   on real audio** — only on unit-test fixtures. Whether metal actually reads red
   is the single biggest open question in Phase 1.

3. **Visual rendering.** The UI builds, serves and compiles, and the payload
   matches its types, but no browser automation was available so it was never
   seen on screen.

## Next steps for the user

Run the 20-song pass described in the plan's Task 20, spanning at least: metal or
hard rock, sad acoustic, pop, blues or jazz, and something in a minor key that is
*not* heavy. Record for each: whether the chords matched by ear, the detected key,
and the dominant colour.

Two decisions come out of it:

- If most charts are wrong, stop before Phase 2 rather than building a scrolling
  play-along on unreliable data.
- If metal still comes out blue, tune `THIRD_RATIO_THRESHOLD` and
  `FLATNESS_THRESHOLD` in `backend/kord/analysis/timbre.py` against the tracks
  that failed, then re-verify.

A known issue to watch: key detection disagreed with itself on the one real track
tested (chord scorer said B major, chroma said F# major; the chroma reading looked
better). Kord handled it correctly by flagging the key uncertain rather than
asserting it, but if the chord scorer is systematically wrong across 20 songs, the
candidate fixes are recorded in
[`2026-08-11-chord-engine-spike.md`](2026-08-11-chord-engine-spike.md).
