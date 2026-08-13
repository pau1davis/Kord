# Kord Phase 2 — Play-along

**Date:** 2026-08-13
**Status:** Approved for implementation
**Builds on:** [Phase 1 design](2026-08-11-kord-design.md)

---

## 1. What this adds

Play a song start to finish while the chord chart follows it, so you can learn the
song with the guitar in your hands. The song view stops being a wall of chord
cards and becomes a play-along screen: one large current chord, a map of the whole
song you can click and loop, and the full chart collapsed underneath.

Four capabilities, chosen together:

1. **Follow along** — the current chord, large, with the next one visible
2. **Loop a section** — pick a range and drill it
3. **Jump to any point** — click the map or a chord to seek there
4. **Bar and beat context** — see where changes land against the beat

---

## 2. What Phase 1 already provides

No new analysis data is needed for sync. Verified against the cached
`Mouth for War` analysis on 2026-08-13:

| Stored | Value |
|---|---|
| Chord segments with `start_s` / `end_s` | 197 |
| Beat grid | 408 beats at 103 BPM |
| `sync_offset_ms` (leading-silence trim) | 511 |
| `time_scale` (speed correction) | 1.0 |

Sections are the one genuinely new analysis output (§5).

---

## 3. Constraints verified before designing

### 3.1 Playback is possible, with conditions

The Web Playback SDK still functions for development-mode apps. It requires:

- **Full Spotify Premium** for the account. Mobile-only tiers (Lite, Mini) do not
  qualify. Since 2026-03-09 Spotify requires dev-mode app *owners* to hold Premium
  regardless, so this is already satisfied.
- **Three additional scopes**: `streaming`, `user-read-email`, `user-read-private`.
  Adding them invalidates the current grant, so re-authorization is required once.

### 3.2 There is no playback-rate control

The SDK cannot slow playback down. Half-speed practice — the most useful thing
when learning a difficult passage — **is not achievable with Spotify as the audio
source** and is explicitly out of scope. Looping is the practice feature that
survives this limitation, which is why it is included.

### 3.3 Sync cannot be measured, only calibrated

Chord timestamps derive from YouTube audio; playback comes from Spotify's master.
Spotify supplies no audio, so the offset between them can never be measured
directly (Phase 1 spec §2.2). It must be set by ear, once per song, and remembered.

### 3.4 Structural segmentation is affordable

Measured on `Mouth for War` (4.5 min): **1.7 s**, producing 8 sections of 6.5–72 s.
Roughly 25% added to the ~6.4 s analysis. Acceptable.

---

## 4. Architecture

Playback lives entirely in the browser because the SDK requires it. The backend
gains little, since Phase 1 already stores the timing data.

```
Browser                                  Server
├─ player.ts        SDK wrapper          ├─ SectionDetector    (new, in pipeline)
├─ useSyncedPosition  interpolation      ├─ SCOPES + streaming
├─ PlayAlong        hero chord           ├─ GET /api/auth/token   (new)
├─ SongMap          sections, loop       └─ PUT /api/track/{id}/offset  (new)
└─ ChordSheet       full chart, collapsed
```

### 4.1 The browser needs an access token

The SDK runs client-side and requires an OAuth token there. Phase 1 deliberately
kept tokens server-side, with the browser never seeing one.

**Phase 2 exposes `GET /api/auth/token` to the local UI.** This is a real
reduction in the Phase 1 security posture, accepted because Kord binds to
`127.0.0.1` and serves one user. It is recorded here explicitly so it is a
decision rather than an oversight, and it is the first thing to revisit if Kord
is ever exposed beyond localhost.

The endpoint returns the current access token, refreshing server-side first if it
has expired, so the SDK's `getOAuthToken` callback stays valid across the
one-hour token lifetime without the user noticing.

---

## 5. Sections

### 5.1 Detection

Agglomerative clustering over stacked chroma and MFCC features. Chroma captures
harmonic change; MFCC captures timbral change, which is what separates a quiet
verse from a loud chorus when the chords are identical — the common case in the
music this is aimed at.

Section count scales with duration rather than being fixed:
`n = clamp(round(duration_s / 30), 4, 12)`, so a two-minute song and a
seven-minute one both get useful granularity.

### 5.2 Labelling

A second pass over the detected sections: take each section's mean feature
vector, cluster by similarity, and assign labels **A, B, C…** in order of first
appearance. A song reads `A B A B C B`.

Labels are deliberately not "verse" and "chorus". The detector knows what
repeats, not what those repeats are called, and naming them would assert more
than the analysis supports.

### 5.3 Storage

`Section(start_s, end_s, label)`, stored on `Analysis` as `sections`. Requires an
engine version bump to **`btc-3`**, which invalidates cached analyses so they
recompute — the same mechanism Phase 1 established.

---

## 6. Sync

### 6.1 Position tracking

The SDK reports position sparsely: on state changes and roughly every few hundred
milliseconds. Between reports, position is extrapolated:

```
estimated_ms = last_position_ms + (performance.now() - last_event_wallclock_ms)
```

**Re-anchored on every state event**, so extrapolation error can never accumulate.
When paused, the elapsed term is zero. Seeks arrive as state events and re-anchor
naturally.

### 6.2 Applying the offset

```
chart_time_s = estimated_ms / 1000 - user_offset_s
```

`user_offset_s` (from `track.user_offset_ms`, §6.3) starts at 0 and is adjusted by ear with arrow keys in 10 ms steps
while the song plays. It is stored **per track**, not per analysis, so
re-analysing a song does not discard calibration the user did by hand.

### 6.3 Two different offsets, kept apart

Phase 1 already stores `sync_offset_ms` on the analysis — 511 ms for
`Mouth for War`. **That is not this offset.** It records how much leading silence
was trimmed from the *YouTube* audio, which is why chord timestamps begin at the
first sound rather than at the file start. It is a property of the analysis.

The Phase 2 offset is a property of *the user's calibration against Spotify's
master*, which no analysis can know. Conflating them would mean re-analysis
silently discarding hand calibration, or a re-download with different padding
shifting a chart the user had already corrected.

They are stored separately:

- `analysis.sync_offset_ms` — unchanged, owned by the pipeline
- `track.user_offset_ms` — new column, owned by the user, written by
  `PUT /api/track/{id}/offset`, defaulting to 0 and surviving re-analysis

### 6.4 Finding the current chord

Binary search over `chord_segments` for the segment containing `chart_time_s`. A
`requestAnimationFrame` loop drives the display.

### 6.5 Looping

When `chart_time_s` passes `loop_end`, seek to `loop_start + user_offset_s`. A
guard interval after each seek prevents a boundary landing mid-frame from firing
repeated seeks. Loop boundaries snap to section edges.

---

## 7. The song view

### 7.1 Hero chord, and the flicker problem

`Mouth for War` changes chord **171 times in 4 minutes**, sometimes twice a
second. Rendering every change in a large display strobes unreadably.

Before display, consecutive segments shorter than **400 ms** collapse into
whichever chord dominates the span. This is a pure function producing a *display
track*; the underlying analysis is untouched and the collapsed chord sheet still
lists every change. The display is a view, not a truncation.

The next chord is shown alongside with its countdown, so the hand can move early.

### 7.2 Song map

A horizontal strip of section blocks, width proportional to duration, with a
playhead travelling through. Click a block to seek. Drag across blocks to set a
loop. The current section is highlighted.

### 7.3 Chord sheet

The full chart from Phase 1, collapsed by default behind a disclosure. Every
chord, every timestamp, low-confidence ones still dashed. Clicking a chord seeks
to it.

### 7.4 Beat context

Beat marks from the stored grid, shown under the hero chord so it is visible
whether a change lands on beat 1. Rendered from `beat_grid.times_s`, shifted by
the same offset as everything else.

---

## 8. Error handling

Ordered by likelihood.

| Condition | Behaviour |
|---|---|
| No Premium | SDK returns `account_error`. Playback controls hidden; charts, theory and mood ring work exactly as in Phase 1. Kord degrades to its current self. |
| Token expires mid-session | SDK re-requests via `getOAuthToken`; the endpoint refreshes server-side. Invisible. |
| Safari | EME support is patchy. Detected and stated plainly rather than failing silently. |
| SDK script unreachable | Play-along disabled with a message; the rest of the page is unaffected. |
| Seek storm at a loop boundary | Guard interval after each seek. |
| Song has no analysis yet | Play-along hidden until analysis completes; existing pending/failed states unchanged. |

**Principle, carried from Phase 1:** every degraded path leaves the Phase 1
experience intact. Playback is additive; nothing that works today may stop
working because playback is unavailable.

---

## 9. Testing

The tricky logic is pure and gets real tests:

- **Position interpolation** — extrapolation between events, re-anchoring, paused
  state, seek handling
- **Current-chord lookup** — binary search including boundaries, gaps, and times
  before the first or after the last segment
- **Loop wrap-around** — crossing the end, the guard interval, offset applied to
  the seek target
- **Short-segment collapsing** — 171 changes reduce to a readable track; the
  dominant chord wins a collapsed span; the underlying data is unmodified
- **Section labelling** — repeated feature vectors get the same label; labels are
  assigned in order of first appearance
- **Section detection** — golden test on synthesised audio with a known A-B-A-B
  structure

The SDK is mocked. No test requires a browser, a network, or a Premium account.

---

## 10. Build order and the gate

**Sync is the risk.** Everything else is decoration on top of it.

1. **Foundation** — scopes, token endpoint, SDK wrapper, position interpolation,
   hero chord following a real song
2. **Gate** — does the chart track a real song convincingly, by ear? If not, stop.
   The map and looping are worthless on a foundation that drifts.
3. **Sections and map** — detection, labelling, engine bump, the map with jump
4. **Looping** — range selection, wrap, guard
5. **Chord sheet and beat context** — collapse the existing chart, add beat marks

---

## 11. Out of scope

- **Slowing playback down** — impossible via the SDK (§3.2)
- **Verse/chorus naming** — the detector knows repetition, not function (§5.2)
- **Sub-section loop precision** — loops snap to section edges; millisecond
  dragging is not the interaction anyone wants
- **Phase 3 items** — aggregate mood ring, recommendations
- **Phase 4 items** — export, bass tablature

---

## 12. Recorded decisions

| Decision | Rationale |
|---|---|
| Layout: hero chord + song map | Chosen from three mockups. The only one where looping and jumping have a natural home. |
| Audio segmentation over chord repetition | Catches quiet-verse-to-loud-chorus where the chords do not change. Costs an engine bump and re-analysis; accepted. |
| Manual nudge over beat-grid snapping | The offset is unmeasurable (§3.3). Snapping would be confidently wrong when it missed by a beat; a nudge is exact after four seconds of work. |
| Offset stored per track, not per analysis | Re-analysing must not discard hand calibration. |
| Access token exposed to the browser | Required by the SDK. Accepted for a localhost single-user tool; recorded as a posture reduction, not an oversight. |
| 400 ms minimum hero display | 171 changes in 4 minutes is unreadable otherwise. A display concern, kept out of the data. |
| Sections labelled A/B/C | The analysis supports "this repeats", not "this is a chorus". |
