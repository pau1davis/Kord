# Kord Phase 2 — Play-along

**Date:** 2026-08-13
**Status:** Approved for implementation
**Builds on:** [Phase 1 design](2026-08-11-kord-design.md)

---

## 1. What this adds

Play a song start to finish while the chord chart follows it, so you can learn the
song with the guitar in your hands — including **slowing it down** to work out a
hard passage. The song view stops being a wall of chord cards and becomes a
play-along screen: one large current chord, a map of the whole song you can click
and loop, and the full chart collapsed underneath.

Five capabilities:

1. **Follow along** — the current chord, large, with the next one visible
2. **Slow down** — 0.5×, 0.75×, 1× with the pitch unchanged
3. **Loop a range** — pick a passage and drill it
4. **Jump to any point** — click the map or a chord to seek there
5. **Bar and beat context** — see where changes land against the beat

---

## 2. The central decision: Kord plays the audio it analysed

Phase 2 was first designed around Spotify's Web Playback SDK. That design was
abandoned for one disqualifying reason and replaced with something simpler.

**Spotify's SDK has no playback-rate control.** Slowing a song down is the single
most useful thing when learning a difficult passage, and it is impossible with
Spotify as the audio source. The audio is DRM-protected, so it cannot be tapped
and re-rendered either.

Kord already downloads audio in order to analyse it, then deletes it. **Keeping
that file and playing it back** solves the problem — and collapses most of the
rest of the design with it:

| | Spotify SDK | Playing the analysed audio |
|---|---|---|
| Slow down | impossible | `playbackRate`, pitch preserved |
| Sync | unmeasurable; calibrated by ear per song | **exact by construction** |
| Drift over a song | possible, needs re-anchoring | impossible — one clock |
| Looping | seek-based, snapped to sections | sample-accurate, any range |
| Premium required | yes | no |
| Re-authorisation | yes, three new scopes | none |
| Works offline | no | yes, once cached |

**The sync problem does not get solved. It stops existing.** Chord timestamps were
derived from this exact file, so playing it means chart time and audio time are
the same clock. There is no offset to calibrate, no nudge control, no drift, and
no gate needed on whether sync can be made to work.

### 2.1 What this costs

- **Audio is retained** rather than deleted. Phase 1 made deletion load-bearing
  because of disk pressure, but that decision was taken when playback was out of
  scope. Roughly 4 MB per song, capped and evicted (§3).
- **It leans harder on yt-dlp.** Analysing downloaded audio is one thing; playing
  it back is a further step. Same personal-machine, same quarantined module, but
  a real escalation of the Phase 1 decision rather than a free one.
- **Practice time no longer counts as Spotify streams**, so it does not reach the
  artist. Small, but a genuine consequence of the switch.
- **Audio is YouTube Opus, not Spotify's master.** Adequate for practice.

Spotify keeps the roles only it can fill: identity, search, metadata, and the
listening history that Phase 3 needs.

---

## 3. Audio retention

Downloads are Opus in a WebM container, 2.6–5.1 MB per song (measured), which
Chrome plays natively. Stored at `~/.kord/audio/{spotify_id}.{ext}`.

**Eviction is least-recently-played, against a configurable cap** (`KORD_AUDIO_CAP_GB`,
default 2 GB — roughly 500 songs). `track.last_played_at` is touched on playback;
when the cap is exceeded, the oldest files are removed until it is not. An evicted
song is not broken: its analysis is cached forever and the audio re-downloads on
next play.

**Analysis never depends on retained audio.** The pipeline continues to work on a
temporary copy and clean up after itself; retention is a separate, explicit copy
into the audio store. A failure to retain must not fail an analysis.

---

## 4. Architecture

```
Browser                              Server
├─ player.ts     <audio> wrapper     ├─ SectionDetector      (new, in pipeline)
├─ usePlayhead   reads currentTime   ├─ AudioStore           (new: retain, evict)
├─ PlayAlong     hero chord          └─ GET /api/track/{id}/audio   (new)
├─ SongMap       sections, loop
└─ ChordSheet    full chart, collapsed
```

No new OAuth scopes. No access token in the browser. The Phase 1 security posture
is unchanged — a direct benefit of dropping the SDK.

### 4.1 Serving audio

`GET /api/track/{id}/audio` streams the stored file and **must support HTTP Range
requests**. The browser issues ranged requests to seek, so without `206 Partial
Content` the scrubber and looping will not work. This is the one piece of server
plumbing with a real failure mode, and it gets a direct test.

Returns 404 when the file has been evicted, which the UI treats as "re-fetch",
not as an error.

---

## 5. Sync, and the correction that must be removed

### 5.1 The only offset is a known constant

Phase 1 trims leading silence before analysis, so chord timestamps start at the
first sound while the file still contains the silence. That amount is already
stored exactly:

```
chart_time_s = audio.currentTime - analysis.sync_offset_ms / 1000
```

`sync_offset_ms` is 511 ms for `Mouth for War`, 46 ms for `Pink Moon`. It is
measured, not guessed. There is nothing for the user to calibrate.

### 5.2 Speed-scaling must stop being applied

Phase 1 rescales chord timestamps and the beat grid by `time_scale` when a
YouTube upload is slightly sped up, so the chart lines up with **Spotify's**
master. Playing the local file makes that correction actively wrong.

This is live, not hypothetical: the cached `Pink Moon` analysis has
`time_scale=0.992`. Playing the local file against rescaled timestamps would
drift about **1.4 seconds over three minutes** — plainly audible.

**Change:** the pipeline stops rescaling timestamps. Detection of speed
adjustment is kept, because a sped-up upload is also pitch-shifted and therefore
makes the detected key unreliable — the `speed_adjusted` flag and its UI warning
stay. Only the timestamp rescaling is removed.

`time_scale` remains on the record as an observation, no longer applied.

### 5.3 Reading the playhead

`audio.currentTime`, read once per `requestAnimationFrame`. No interpolation, no
event anchoring, no extrapolation — the element exposes an exact clock on demand.
The `usePlayhead` hook is a handful of lines where the SDK version needed careful
drift handling.

### 5.4 Finding the current chord

Binary search over `chord_segments` for the segment containing `chart_time_s`.

### 5.5 Looping

When `chart_time_s` passes `loop_end`, set
`audio.currentTime = loop_start + sync_offset_s`. Sample-accurate and immediate,
so no seek-storm guard is needed. Ranges are arbitrary; section edges are offered
as convenient snap points, not imposed.

---

## 6. Slowing down

`audio.playbackRate` at 0.5×, 0.75× or 1×, with `preservesPitch` left at its
default of `true` so the song stays in the same key. Supported across all current
browsers since December 2023, reliable across 0.25–4.0.

Chart timing needs no adjustment whatsoever: `currentTime` advances in real
seconds of *audio*, so chord times continue to match at any rate. This falls out
of using one clock.

Rate is per-session, not persisted — it is a practice mode, not a property of the
song.

---

## 7. Sections

### 7.1 Detection

Agglomerative clustering over stacked chroma and MFCC features. Chroma captures
harmonic change; MFCC captures timbral change, which is what separates a quiet
verse from a loud chorus when the chords are identical.

Section count scales with duration: `n = clamp(round(duration_s / 30), 4, 12)`.

Measured cost on `Mouth for War` (4.5 min): **1.7 s**, producing 8 sections of
6.5–72 s. About 25% added to the ~6.4 s analysis.

### 7.2 Labelling

Each section's mean feature vector is clustered by similarity, and labels **A, B,
C…** are assigned in order of first appearance. A song reads `A B A B C B`.

Not "verse" and "chorus": the detector knows what repeats, not what those repeats
are called, and naming them would assert more than the analysis supports.

### 7.3 Storage

`Section(start_s, end_s, label)` on `Analysis`. Requires an engine bump to
**`btc-3`**, which also picks up the removal of timestamp rescaling (§5.2).

---

## 8. The song view

### 8.1 Hero chord, and the flicker problem

`Mouth for War` changes chord **171 times in 4 minutes**, sometimes twice a
second. Rendering every change in a large display strobes unreadably.

Before display, consecutive segments shorter than **400 ms** collapse into
whichever chord dominates the span — a pure function producing a *display track*.
The analysis is untouched and the collapsed chord sheet still lists every change.
The display is a view, not a truncation.

The next chord is shown alongside with its countdown, so the hand can move early.

### 8.2 Song map

A horizontal strip of section blocks, width proportional to duration, with a
playhead travelling through. Click to seek. Drag to set a loop. Current section
highlighted.

### 8.3 Chord sheet

The Phase 1 chart, collapsed by default behind a disclosure. Every chord, every
timestamp, low-confidence ones still dashed. Clicking a chord seeks to it.

### 8.4 Beat context

Beat marks from the stored grid under the hero chord, so it is visible whether a
change lands on beat 1.

---

## 9. Error handling

| Condition | Behaviour |
|---|---|
| Audio evicted | 404 from the audio endpoint; UI re-requests analysis, which re-downloads. Presented as a short wait, not an error. |
| Audio never retained (analysed before Phase 2) | Same path as eviction — re-download on first play. |
| Range requests unsupported by the server | Seeking and looping silently break. Directly tested (§4.1) rather than trusted. |
| Disk cap reached | Eviction runs before writing. If a single file still will not fit, playback is refused with a clear message rather than filling the disk. |
| Decode failure in the browser | Play-along hidden; chart, theory and mood ring unaffected. |
| Song has no analysis yet | Play-along hidden until analysis completes; existing pending and failed states unchanged. |

**Principle, carried from Phase 1:** every degraded path leaves the Phase 1
experience intact. Playback is additive; nothing that works today may stop working
because playback is unavailable.

---

## 10. Testing

The tricky logic is pure and gets real tests:

- **Current-chord lookup** — binary search including boundaries, gaps, and times
  before the first or after the last segment
- **Chart-time conversion** — `currentTime` minus the trim offset, including a
  song with a non-zero trim
- **Loop wrap-around** — crossing the end, the seek target including the offset
- **Short-segment collapsing** — 171 changes reduce to a readable track; the
  dominant chord wins a collapsed span; the source data is unmodified
- **Section labelling** — repeated feature vectors get the same label; labels
  assigned in order of first appearance
- **Section detection** — golden test on synthesised audio with a known A-B-A-B
  structure
- **Range requests** — a ranged GET returns `206` with correct `Content-Range`
  and the right bytes
- **Eviction** — least-recently-played goes first; the cap is respected; an
  evicted song keeps its analysis
- **No rescaling** — a `speed_adjusted` track keeps unscaled timestamps while
  retaining its flag

The `<audio>` element is mocked. No test needs a browser, a network, or Premium.

---

## 11. Build order

Sync is no longer a risk, so there is no gate. The order is simply
dependency-driven:

1. **Retention and serving** — AudioStore, the audio endpoint with Range support,
   eviction
2. **Playback and follow-along** — `<audio>` wrapper, playhead, hero chord,
   rate control
3. **Sections** — detection, labelling, engine bump, removal of rescaling
4. **Map, looping and jumping**
5. **Chord sheet and beat context**

Step 2 is the first point where the feature is genuinely usable, and worth
stopping at to look.

---

## 12. Out of scope

- **Spotify playback** — removed entirely from Phase 2 (§2)
- **Verse/chorus naming** — the detector knows repetition, not function (§7.2)
- **Pitch shifting / capo transposition** — a plausible future feature, not this one
- **Phase 3** — aggregate mood ring, recommendations
- **Phase 4** — export, bass tablature

---

## 13. Recorded decisions

| Decision | Rationale |
|---|---|
| Play the analysed audio, not Spotify | Spotify's SDK cannot slow playback down, which is the point of the feature. Playing the analysed file also makes sync exact rather than calibrated, and removes the Premium and re-auth requirements. |
| Retain audio, evict least-recently-played | Phase 1's delete-always rule was set when playback was out of scope. 2 GB holds ~500 songs; an evicted song keeps its analysis and re-downloads on demand. |
| Stop rescaling timestamps by `time_scale` | The correction existed to match Spotify's master. Against local audio it introduces ~1.4 s of drift over three minutes on `Pink Moon`, which is cached and speed-adjusted today. |
| Keep the `speed_adjusted` flag | A sped-up upload is pitch-shifted, so the detected key stays unreliable even though the timing correction is gone. |
| Layout: hero chord + song map | Chosen from three mockups. The only one where looping and jumping have a natural home. |
| Audio segmentation over chord repetition | Catches quiet-verse-to-loud-chorus where chords do not change. Costs an engine bump, accepted. |
| 400 ms minimum hero display | 171 changes in 4 minutes is unreadable otherwise. A display concern, kept out of the data. |
| Sections labelled A/B/C | The analysis supports "this repeats", not "this is a chorus". |
| Rate not persisted | Practice speed is a mode, not a property of the song. |
