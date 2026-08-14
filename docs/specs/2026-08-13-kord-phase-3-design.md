# Kord Phase 3 — playable facts, taste, and parts

**Status:** design, awaiting review
**Date:** 2026-08-13

## 1. What this phase is for

Phase 1 answered "what chords are in this song?". Phase 2 made it playable in
time with the record. Phase 3 answers the questions a player actually asks
next: *what do I tune to, what tempo is this really, what does my taste look
like, and can I hear just the bass part?*

Two of these start as bug fixes. Kord currently reports Mercy Mercy Me at
184.6 BPM against a true ~93, and there is no tuning information at all — so a
down-tuned song silently produces shapes that do not fit the record.

### Goals

1. Correct tempo, and a beat grid that matches it.
2. Tuning: what is measurable, measured; what is inferred, labelled as such.
3. A home screen showing your taste — record art in slow orbit, coloured by
   the harmony of the music you actually listen to.
4. Stem separation on demand, so each part can be soloed or muted.

### Non-goals

- Note-level tab transcription (see §9).
- Multi-user, hosting, or anything that leaves this machine.
- Recommendations. Spotify's recommendation and `audio-features` endpoints
  were withdrawn in the November 2024 cull; any future version has to be built
  on Kord's own analysis, and that is not this phase.

## 2. Part 0 — shared foundation

Everything below depends on two changes.

### 2.1 Retained audio becomes m4a

`YouTubeAudioSource.download` currently takes `bestaudio/best`, which on
YouTube is usually WebM/Opus. Measured on a retained file:

```
format_name  = matroska,webm
format dur   = 237.701
stream dur   = N/A          <- no stream duration
```

No stream duration and no seek index. Such a file plays linearly but seeks
poorly, Safari may refuse it outright, and it is a poor input to Demucs.

**Change:** request `bestaudio[ext=m4a]/bestaudio/best`, and derive the audio
endpoint's `content-type` from the file extension rather than hardcoding it.

This is also the most likely fix for the intermittent "song cuts off partway"
report. That was not reproducible at the time of writing, and the server was
cleared as a cause — an open-ended `Range: bytes=0-` returns all 3,740,154
bytes with correct `content-range`. The missing seek index is the leading
remaining explanation, but this is a **suspected** fix, not a confirmed one,
and must be re-tested by ear once m4a lands.

### 2.2 Engine version bump to `btc-4`

Cached analyses hold wrong tempos and point at WebM files. `engine_version`
already exists precisely so that improving the analyser invalidates stale
results rather than mixing engine outputs. One bump re-runs analysis on next
view, which re-downloads as m4a — a single migration path for both fixes. No
bespoke migration code.

## 3. Part 1 — tempo octave correction

### 3.1 The defect

`BeatTracker.track` calls `librosa.beat.beat_track(y=y, sr=sr, units="frames")`
with defaults. Its `start_bpm=120` log-normal prior mis-locks an octave high on
slower material. Reproduced:

| | Mercy Mercy Me (Marvin Gaye) |
|---|---|
| reported tempo | 184.6 BPM |
| median beat gap | 0.3251 s (= 184.6 BPM) |
| beats | 567 over 182 s |
| true tempo | ~93 BPM |

The grid itself is double-time, not just the label, so `BeatStrip` draws twice
as many beats as the song has.

### 3.2 Why the obvious test does not work

A doubled grid always fits the audio, because the true beats are a subset of
it. Goodness-of-fit therefore cannot distinguish 92 from 184. The
disambiguating signal is *which* beats carry onset energy.

### 3.3 The correction

```
onset_env = librosa.onset.onset_strength(y=y, sr=sr)
strength  = onset_env[beat_frames]
even, odd = mean(strength[0::2]), mean(strength[1::2])
```

If one phase is consistently weaker than the other, the grid is double-time:
keep the stronger phase, halve the tempo. In genuinely fast music every beat
carries comparable energy and the grid is left alone.

Guards:

- Only consider halving when the detected tempo exceeds 130 BPM, so a true
  100 BPM can never become 50.
- Require a clear margin between phases (weaker/stronger below a threshold
  fixed during implementation against real songs) — an ambiguous result leaves
  the grid untouched. Preferring the original on ambiguity means the failure
  mode stays "unchanged", never "confidently halved in error".
- Halving must decimate the grid *and* the tempo together. They are one fact
  and may never disagree.

### 3.4 Testing

Fully testable without any download, using synthesised click trains:

- Alternating strong/weak accents at 180 BPM -> reports 90, grid gap doubles.
- Uniform clicks at 180 BPM -> stays 180, grid untouched.
- Uniform clicks at 100 BPM -> stays 100 (guard holds).
- Silence -> unchanged from today's empty-grid behaviour.

Plus a regression test asserting tempo and median beat gap always agree.

## 4. Part 2 — tuning

> **Revised 2026-08-14 after prototyping. Part 2 now depends on Part 4 and is
> built after it.** Measurement on real songs showed the two halves of this
> part have very different reliability:
>
> - **Reference pitch works.** A circular median of `estimate_tuning` over 30 s
>   windows is stable: Mercy Mercy Me reads 7, 7, 6, 7, 6, 4 cents. It must be a
>   circular statistic — Mouth for War reads 49, 49, 48, 47, −43, −50, 42, which
>   is one value near the ±50 wraparound, not a spread of 99 cents.
> - **Lowest sounding note does not.** Every method tried on the full mix —
>   CQT energy, sustained presence, harmonic support, harmonic-sum salience on
>   the harmonic component — either returns the bottom bin (sub-bass rumble) or
>   moves by one to two semitones with the threshold. The harmonic-supported
>   detector returns D♯1 (38.9 Hz) for Mercy Mercy Me, below the low E of a
>   bass guitar. A semitone of error is exactly the E-standard/Eb-standard
>   distinction, so the naming built on top of it would be worthless.
>
> Naming a tuning from that number would make Kord confidently wrong with
> nothing to check it against — the outcome §4.2 exists to avoid.
>
> **Resolution:** build Part 4 first. Detecting the lowest note of an isolated
> guitar stem is a far easier problem than from a full mix, because the rumble,
> the bass and the drums are gone. Part 2 is then built on the stem, and keeps
> the naming promise below intact rather than diluting it.

### 4.1 What is measurable and what is not

If a whole band tunes down a semitone, the recording remains perfectly in
12-TET — it is simply in a different key. **Tuning is therefore not directly
measurable from pitch.** Two things are:

- **Deviation from A440**, via `librosa.estimate_tuning`, which returns a float
  in `[-0.5, 0.5)` as a fraction of a semitone (x100 = cents). This catches
  tape-speed drift and A432-style references, not whole-step down-tuning.
- **Lowest sustained pitch**, via a low-register CQT with an energy-and-duration
  threshold, so a passing sub-bass artefact cannot masquerade as the tuning.

The named tuning is **inferred** from those two plus the detected key.

### 4.2 Honest output

Per the review decision, Kord names a tuning *and* shows its evidence:

> **Likely Drop D or D standard** — lowest note D2, 3¢ flat of A440

Drop D and D standard share a lowest note and cannot be told apart from audio;
both are named rather than one being picked arbitrarily. Candidates are drawn
from a table of common tunings (E standard, Eb standard, D standard, Drop D,
Drop C#, Drop C, and their bass equivalents).

Two caveats the UI must carry, because they are the realistic failure modes:

- Bass typically doubles guitar an octave down, so the lowest note in the mix
  may be the bass rather than your low string. The display states which
  register the note was found in.
- A song can simply be *written* low without being down-tuned. Confidence is
  reported, and low confidence reads as "can't tell" rather than a guess.

### 4.3 Data shape

`Analysis` gains a `tuning` field:

```python
@dataclass
class Tuning:
    reference_cents: float      # deviation from A440, -50..+50
    lowest_note: str            # e.g. "D2"
    lowest_midi: int
    candidates: list[str]       # e.g. ["Drop D", "D standard"]
    string_pitches: list[str]   # e.g. ["D2","A2","D3","G3","B3","E4"]
    confidence: float
```

`string_pitches` is structured rather than a display string specifically so
the deferred chord-diagram work (§9) can consume it. Fingerings are a function
of chord plus tuning; encoding tuning as prose now would force that to be
re-derived later.

Surfaced through `/api/track/{id}` as a `tuning` object and rendered in
`TheoryPanel`, alongside key and tempo.

### 4.4 Testing

Synthesised material with known content: a tone at a known frequency detuned by
a known number of cents asserts `reference_cents`; a synthesised low D2 asserts
`lowest_note`; a chord voicing above a known lowest note asserts candidate
selection. Inference is a pure function over (lowest_midi, key,
reference_cents) and gets table-driven tests independent of any audio.

## 5. Part 3 — the taste home screen

### 5.1 Navigation

The wordmark becomes a button returning to home. Two views (`"home" | "song"`)
held as state in `App` — a router is not justified for two views and would be
the larger change.

### 5.2 Where the colour comes from

`audio-features` is gone, so "the vibe of my music taste" cannot come from
Spotify. It comes from Kord's own analysis, via `build_palette(segments,
heaviness)`, which the Phase 1 design already specified as working for "one
song or many" — the aggregate ring needs no new palette code, only more
segments.

On first visit, `/api/me/top` (Spotify `user-top-read`, which survived the
cull) returns your top tracks and they are enqueued into the **existing** job
queue for background analysis. Roughly 30 s per track, so ~25 minutes for 50,
once, then cached forever.

**Verified against the live account on 2026-08-13**, rather than assumed:
`GET /v1/me/top/tracks?limit=50` returns 200 with 50 items (`total: 2094`).
The February 2026 development-mode change that cut `limit` to 10 applies to
`/v1/search` only, not here — worth recording, because the November 2024 cull
makes "this endpoint still works" an unsafe assumption in this codebase.

Consequence, stated plainly: the screen is useful immediately from metadata —
record art, titles — and gains colour progressively as songs finish. It is not
fully coloured on first load, and pretending otherwise would be designing for a
screenshot rather than for use.

Tracks flagged `speed_adjusted` are excluded from aggregation, as the Phase 1
design requires: a sped-up upload is pitch-shifted, so its key and therefore
its colour are unreliable.

### 5.3 The orbit

Record art drifts slowly around a circle. CSS transforms only, so it composites
on the GPU rather than thrashing layout, and `prefers-reduced-motion` disables
the motion — the codebase already honours that for the analysis pulse.

Art comes from Spotify's CDN URLs already present in `TrackSummary.image`. No
new storage.

### 5.4 Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/me/top` | top tracks (proxied, cached briefly) |
| `POST /api/me/top/analyze` | enqueue un-analysed top tracks |
| `GET /api/me/taste` | aggregate palette + per-track analysis status |

## 6. Part 4 — stem separation

### 6.1 Model choice

Default `htdemucs` separates drums / bass / other / vocals — **guitar is not a
stem; it lands in "other"**. Since the stated purpose is learning the guitar
part, this requires `htdemucs_6s`, which adds explicit guitar and piano. Slower,
and the difference between the feature working for this user and not.

Demucs is a new dependency. `torch` 2.13.0 is already installed and reports
`mps.is_available() == True`, so the M1 GPU is usable.

### 6.2 Execution

On demand per song, as a new job type reusing the existing queue rather than a
parallel mechanism. Stems are written under `~/.kord/stems/{id}/` and counted
against the existing LRU cap, so the disk ceiling stays one number.

### 6.3 Playback

Six stems cannot be six `<audio>` elements: each has its own clock and they
drift. The stems view uses Web Audio — one `AudioContext`, a `GainNode` per
stem for mute/solo, all sources started against the same clock so drift is
structurally impossible.

Decoded **mono**. Practice does not need stereo, and it halves memory to
roughly 250 MB for six stems, which matters on an 8 GB machine also hosting
torch.

This is a second playback path alongside the Phase 2 `<audio>` player. That is
real added complexity and is accepted deliberately: retrofitting the existing
player to Web Audio would put the working play-along view at risk for no gain
to songs without stems.

### 6.4 Risks

- Demucs on MPS has known instability; a CPU fallback (slower) may be needed.
  The job must fail gracefully to "stems unavailable" rather than failing the
  song.
- Separation quality on dense mixes is imperfect. Stems are a practice aid, not
  a master, and the UI should not imply otherwise.

## 7. Data model changes

```
analysis   + tuning JSON          (Part 2)
           engine_version -> btc-4 (Part 0, invalidates cache)
stems      spotify_id FK, model, state, error, created_at
```

No destructive migration: the engine bump re-derives everything.

## 8. Testing strategy

Per part, the boundary that matters:

- **Tempo** — synthesised click trains, no network, no model. Pure DSP.
- **Tuning** — synthesised tones for measurement; table-driven pure-function
  tests for inference.
- **Taste** — aggregation is a pure function over analyses and gets unit tests;
  the Spotify proxy is tested with a fake client, as `FakeSpotify` already does.
- **Stems** — the job lifecycle is tested with a fake separator. The model
  itself is not unit-tested; it is a third-party model and asserting its output
  would test Demucs, not Kord.

## 9. Deferred — tab and chord diagrams

Requested during review, explicitly deferred. Recorded so the design does not
foreclose it.

Two different problems, often conflated:

- **Chord diagrams / finger shapes.** A function of chord (root + quality) and
  tuning, both of which Kord will have after Part 2. Generated, not scraped —
  no third-party data and no licensing question. Tractable.
- **Note-level tab of a riff.** Polyphonic transcription, materially harder
  than chord recognition and a research-grade problem. Not implied by the
  first, and should not be promised alongside it.

Part 2's `string_pitches` exists to make the first of these cheap when it comes.

## 10. Build order

1. Part 0 — m4a + engine bump. Everything else assumes it. **Done.**
2. Part 1 — tempo. Small, self-contained, fixes wrong output already shipped.
   **Done.**
3. Part 4 — stems. Largest, and the only part introducing a new dependency.
   Moved ahead of Part 2 on 2026-08-14: see the note at the head of §4.
4. Part 2 — tuning, built on the isolated guitar stem from Part 4.
5. Part 3 — taste home screen. Depends on nothing above except a working queue.

Each part gets its own implementation plan. One plan spanning all five would be
too large to execute or review sensibly.

## 11. Open questions

None blocking. Two to settle during implementation, both empirical rather than
architectural:

- The exact phase-margin threshold in §3.3, to be fixed against a handful of
  real songs of known tempo rather than guessed here.
- Whether Demucs runs acceptably on MPS or needs the CPU fallback (§6.4).
