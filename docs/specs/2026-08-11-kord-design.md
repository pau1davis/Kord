# Kord — Design

**Date:** 2026-08-11
**Status:** Approved for Phase 1 implementation
**Scope of this document:** Phase 1 in implementable detail; Phases 2–4 defined as scope boundaries so the architecture stays open to them.

---

## 1. What Kord is

A personal, local-first web app that connects to Spotify and shows you the music theory behind the songs you listen to: chord charts, key, scale, and an ambient "mood ring" whose color is driven by the chord qualities in your music. It recommends songs you'd enjoy and songs that share the harmonic feel you gravitate toward.

**Audience:** the author, plus a handful of friends at most. Not a public product. This decision drives everything below — it is why local-first, SQLite, and yt-dlp are acceptable choices.

---

## 2. Hard constraints discovered before design

These are not assumptions. They were verified against Spotify's developer documentation and change log on 2026-08-11.

### 2.1 Spotify deprecations (effective 2024-11-27, all new apps)

The following endpoints return `403` for any app created after that date. There is no waitlist and no access path.

| Endpoint | What it gave | Consequence for Kord |
|---|---|---|
| `GET /audio-features` | key, mode, tempo, energy, valence | We derive all of this ourselves |
| `GET /audio-analysis` | beat grid, segments, pitch content | We derive this ourselves |
| `GET /recommendations` | song recommendations | We build our own recommender |
| `GET /artists/{id}/related-artists` | artist similarity | Replaced by Last.fm |
| `preview_url` (30s MP3) | short audio sample | Nulled out; no Spotify audio at all |

### 2.2 Spotify gives us zero audio bytes, ever

The Web Playback SDK streams full tracks but is DRM-protected via Encrypted Media Extensions. The audio cannot be read by the Web Audio API. Combined with `preview_url` being nulled, **there is no path to Spotify audio.** All analysis must run on audio obtained elsewhere.

### 2.3 What Spotify still provides, and it is enough

OAuth login, search, track/album/artist metadata, top tracks and artists (short/medium/long term), recently played, saved tracks, playlists, artist genre tags, and full-track playback via the Web Playback SDK (requires full desktop-tier Premium; Lite and Mini do not qualify).

### 2.4 Consequence: the central architectural split

**Spotify is the player and the taste engine. A separate pipeline is the analyst. The two meet only at a timestamp** (`position_ms` from the SDK).

---

## 3. Target hardware

Apple M1, 8 cores, **8 GB RAM**, **20 GB free disk**, arm64. Python 3.11 and Homebrew present; `ffmpeg` and `yt-dlp` need installing.

Two design consequences, both load-bearing:

- **8 GB rules out Demucs stem separation as a Phase 1 dependency** (4–7 GB per full song → swapping and multi-minute runs). Deferred to Phase 4 as per-song opt-in.
- **20 GB free means audio is deleted immediately after analysis.** Analysis JSON is a few KB per track versus ~8 MB of audio, so the cache can hold thousands of songs without threatening the disk. Nothing needs the audio a second time.

---

## 4. Goals and non-goals

**Phase 1 goals**
- Log in with Spotify
- Search for any song
- Produce a correct chord chart for it, with per-chord timestamps stored (displayed as a static chart in Phase 1; the timestamps are what Phase 2 scrolls against)
- Show key, mode, scale, and Roman numerals
- Show that song's mood ring
- Cache everything so the second view is instant

**Phase 1 non-goals** — deliberately excluded, each landing in a later phase: playback and play-along sync (2), aggregate mood ring across listening history (3), recommendations (3), PDF/MIDI export (4), bass tablature (4), multi-user support and hosting (never, under current scope).

**Success criterion for Phase 1:** for a personally chosen set of 20 songs across genres, the generated chord chart is accurate enough to play along with by ear, and the mood ring visibly distinguishes heavy songs from sad ones. If this fails, the project stops here rather than building a play-along engine on unreliable data.

---

## 5. Architecture

Three processes, all local.

```
Browser (React + TS + Vite)          Server (Python 3.11 / FastAPI)      Worker (Python 3.11, separate process)
├─ Search & song view                ├─ SpotifyClient (OAuth PKCE)       ├─ AudioSource      ← quarantined
├─ Chord chart + theory              ├─ AnalysisQueue                    ├─ ChordRecognizer
├─ Mood ring                         ├─ Recommender        (Phase 3)     ├─ TimbreProfiler
└─ Player                (Phase 2)   └─ SQLite cache                     ├─ KeyDetector
                                                                         └─ BeatTracker
```

**Why Python for the backend rather than Node:** the entire analysis stack is Python. A Node backend would require maintaining a language bridge for no benefit. Node is still used for the frontend build (Vite).

**Why the worker is a separate process:** an analysis that crashes or exhausts memory must not take the UI down with it. On 8 GB this is a real risk, not a theoretical one.

### 5.1 Component interfaces

Each unit has one purpose, a defined interface, and is testable in isolation.

```python
class AudioSource(Protocol):
    def fetch(self, artist: str, title: str, duration_ms: int) -> AudioCandidate | None: ...
```
Returns a local audio path plus the metadata needed to validate the match. **This is the only module that knows about yt-dlp.** Implementations: `YouTubeAudioSource` (Phase 1), `LocalFileAudioSource` (trivial, useful for tests and for songs you own).

```python
class ChordRecognizer(Protocol):
    def recognize(self, audio: Path) -> list[ChordSegment]: ...
    # ChordSegment: start_s, end_s, root, quality, confidence
```

```python
class TimbreProfiler(Protocol):
    def profile(self, audio: Path, segments: list[ChordSegment]) -> list[ChordSegment]: ...
```
Reclassifies segments as `power` where the third is absent and distortion is present. See §7.

```python
class KeyDetector(Protocol):
    def detect(self, audio: Path, segments: list[ChordSegment]) -> KeyEstimate: ...
```

```python
class BeatTracker(Protocol):
    def track(self, audio: Path) -> BeatGrid: ...
```

```python
def build_palette(analyses: Iterable[Analysis]) -> list[PaletteStop]: ...
```
Pure function. Takes one analysis (single-song ring) or many (Phase 3 aggregate ring) — identical code path for both.

---

## 6. Analysis pipeline

1. **Resolve** — `AudioSource.fetch()` searches YouTube for `artist title`, collects candidates.
2. **Validate the match** — compute `ratio = spotify_duration / candidate_duration` and apply a three-tier rule. This filters live cuts, covers, remixes, and extended edits. If no candidate passes, the track is marked `unavailable` rather than analyzed badly.

   | `ratio` | Action |
   |---|---|
   | within `0.995–1.005` | Accept as clean. No correction. |
   | within `0.98–1.02` | Accept, apply linear time-scale correction (§6 step 3), set the `speed_adjusted` flag |
   | outside `0.98–1.02` | Reject the candidate and try the next one |

3. **Correct for speed manipulation** — a significant share of YouTube uploads are sped up 1–2% to evade Content ID. Left uncorrected this causes chart drift *and a wrong detected key*, which would poison the mood ring. Multiply all timestamps by `ratio`. Because a speed change shifts pitch along with tempo, and the widest accepted ratio of 1.02 corresponds to roughly a third of a semitone — enough to land key detection between semitones — any track carrying the `speed_adjusted` flag has its key marked unreliable in the UI and is **excluded from mood ring aggregation** in Phase 3 rather than contributing a possibly-wrong color.
4. **Decode** — ffmpeg → mono, 22050 Hz, WAV. Trim leading silence, recording the trim amount as the initial sync offset.
5. **Analyze** — chords, timbre reclassification, key, beat grid.
6. **Persist** — write `Analysis` JSON to SQLite, stamped with `engine_version`.
7. **Delete the audio file.** Unconditionally, including on failure paths.

### 6.1 Engine selection and the opening spike

**Primary:** BTC (Bi-directional Transformer for Chord recognition, ISMIR-19) — PyTorch, runs on arm64, pretrained weights, large vocabulary covering triads, 7ths, diminished, augmented, and suspended chords. The large vocabulary is a requirement, not a nicety: the mood ring's palette is defined over chord qualities, so a triads-only engine would collapse it to warm-versus-blue.

**Fallback:** Chordino / NNLS-Chroma via `vamp`, if BTC proves unworkable on this machine.

**Phase 1 opens with a timeboxed spike** validating the primary engine against a handful of songs whose chords are known, before any UI work. Decision criteria: installs cleanly on arm64/Python 3.11, runs a 4-minute song within 8 GB in under 90 seconds, and produces recognizably correct chords. If it fails any of these, switch to the fallback and accept the reduced vocabulary, adjusting the palette accordingly.

**Key detection:** cross-check two independent estimates — chroma-based Krumhansl-Schmuckler, and best-fit over the recognized chord sequence. Agreement raises confidence; disagreement lowers it and is surfaced in the UI.

**Beat tracking:** `librosa.beat.beat_track`. Only strictly needed for Phase 2 scrolling, but computed and stored in Phase 1 since the audio is already decoded and will not be available later.

---

## 7. The mood ring

**Hue is driven by chord quality.** Chosen over key-and-mode mapping, which cannot distinguish metal from sad folk since both live in minor keys.

| Quality | Hue | Rationale |
|---|---|---|
| `power` (no third) | 0° red | Heaviness |
| `major`, `major7` | 40° gold | Brightness |
| `dominant7` | 30° amber | Bluesy warmth |
| `sus2`, `sus4` | 170° teal | Unresolved, open |
| `minor`, `minor7` | 220° blue | Sadness |
| `diminished`, `augmented`, `dim7`, `half-dim7` | 285° purple | Instability, tension |

**Unlisted qualities fall back to their family root.** The engine's vocabulary is wider than this table (`maj6`, `min6`, `minmaj7`, and others), so mapping is by family — anything major-family resolves to 40°, minor-family to 220°, diminished-family to 285° — and the table above only overrides where a quality deserves its own hue. No chord is ever dropped for being unrecognized.

**Weight** = summed duration of segments of that quality ÷ total analyzed duration. Stops are normalized and rendered as drifting blurred blobs, so a varied taste renders as several colors flowing in proportion — the behavior originally asked for.

### 7.1 Why a power-chord detector is required

Chord recognizers do not emit "power chord" as a class. A distorted E5 is labeled E major or E minor, and metal is usually in a minor key regardless — so **on chord labels alone, metal and sad acoustic music both render blue**, which is precisely the failure the mood ring exists to avoid.

`TimbreProfiler` supplies the missing class. For each segment it compares chroma energy at the third scale degree against energy at the root and fifth; when the third is weak *and* spectral flatness indicates distortion, the segment is reclassified as `power`. This stays harmony-driven rather than tempo-driven, honoring the chosen design — it only gives the recognizer the one category it structurally cannot produce.

---

## 8. Data model (SQLite)

```
track          spotify_id PK, artist, title, album, duration_ms, isrc, first_seen_at
analysis       spotify_id PK/FK, status, engine_version, key, mode,
               tempo, beat_grid JSON, chord_segments JSON, chord_histogram JSON,
               timbre JSON, key_confidence, chord_confidence_mean,
               source_url, source_duration_ms, time_scale, sync_offset_ms,
               flags JSON, error, analyzed_at
job            id PK, spotify_id FK, state, attempts, error, created_at, updated_at
auth           singleton row: refresh_token, scopes, obtained_at
```

`engine_version` exists so that improving the analyzer invalidates stale cached results rather than silently mixing engine outputs. `sync_offset_ms` is written in Phase 1 (from silence trimming) and made user-adjustable in Phase 2.

---

## 9. HTTP API (Phase 1)

```
GET  /api/auth/login            → redirect to Spotify (OAuth PKCE)
GET  /api/auth/callback         → exchange code, store refresh token
GET  /api/auth/status           → { authenticated: bool }
GET  /api/search?q=             → Spotify search results
GET  /api/track/{id}            → metadata + analysis (or status if pending)
POST /api/track/{id}/analyze    → enqueue job, idempotent
GET  /api/track/{id}/events     → SSE progress stream
GET  /api/health
```

Tokens live server-side only. The browser never sees a Spotify secret.

---

## 10. Error handling and degradation

Ordered by likelihood.

| Condition | Behavior |
|---|---|
| No Premium | Phase 2 playback disabled; charts, theory, and mood ring fully functional. Kord stays useful without a subscription. |
| No audio candidate passes duration validation | Track marked `unavailable` with a plain message; user may paste a YouTube URL manually |
| Speed-manipulation flag triggered | Chart shown with an explicit warning banner; key marked unreliable |
| Analysis crash / OOM | Separate process dies alone; job records reason; retry available; UI unaffected |
| Low chord confidence | Segments below threshold render **dashed and greyed**, never as confident output |
| Key estimates disagree | Key shown with a visible uncertainty marker |
| Spotify token expired | Silent refresh; on refresh failure, re-auth prompt |
| Disk pressure | Audio is deleted immediately after analysis regardless of outcome |

**Principle:** for a tool you are learning from, visible uncertainty is strictly better than a confident lie. Every uncertainty path surfaces rather than hides.

---

## 11. Testing

The genuinely tricky logic is pure functions, so it is cheap to test properly.

**Unit tests (fast, no I/O):** chord→quality→hue mapping; palette weighting and normalization; Roman numeral derivation from key and chord root; scale suggestion; duration-ratio validation and time-scale correction; the semitone-shift flag; playhead interpolation math (Phase 2).

**Golden-file tests:** the analyzer runs against short public-domain audio clips with hand-verified chords, asserting recognized chords within tolerance. Detects regressions when the engine or its parameters change.

**Contract tests:** `AudioSource` is mocked everywhere. **Tests never hit the network** — they stay fast and do not depend on YouTube or Spotify cooperating. Spotify and Last.fm clients are tested against recorded fixtures.

---

## 12. Later phases (scope only)

**Phase 2 — Play-along.** Web Playback SDK, playhead sync with local interpolation between sparse SDK state events, a per-song manual nudge slider persisted to `sync_offset_ms`, and the chart scrolling against the beat grid.

**Phase 3 — Taste and the aggregate ring.** Import top tracks, batch-analyze in the background (~50 tracks × ~30s ≈ 25 minutes, once), aggregate mood ring across listening history via the same `build_palette` function, and two recommenders: Last.fm similarity seeded from Spotify top tracks, and harmonic-fingerprint matching over the local cache. Harmonic matching needs no external service, so it remains available when Last.fm is not.

**Phase 4 — Export and tablature.** PDF chord charts and MIDI export. Demucs stem separation plus `basic-pitch` note transcription for bass tablature, opt-in per song given the memory cost on 8 GB.

---

## 13. Recorded decisions

| Decision | Rationale |
|---|---|
| Personal tool, not a product | Avoids Spotify's 25-user quota review and commercial chord licensing entirely |
| yt-dlp as audio source | Near-total song coverage and full automation. Violates YouTube's ToS, so it is confined to a personal machine and **isolated behind `AudioSource`** — one file to replace if Kord ever goes public. Chosen with this tradeoff understood. |
| Delete audio after analysis | 20 GB free disk; nothing needs the audio twice |
| Hue from chord quality, not key | Key-based mapping cannot separate metal from sad folk |
| Deep chord model over chroma-based | The mood ring's palette requires a chord vocabulary beyond major/minor triads |
| Demucs deferred to Phase 4 | 8 GB RAM makes it slow and memory-pressured; not needed until bass tabs |
| No "mark as learned" progress tracking | Both chosen recommendation strategies work from Spotify history alone, with no manual input |
| Python backend | The analysis stack is Python; a Node backend would add a language bridge for no gain |

---

## 14. Setup prerequisites

`brew install ffmpeg yt-dlp`, a Python 3.11 virtualenv, a Spotify developer app with `http://127.0.0.1:8000/api/auth/callback` registered as a redirect URI, and scopes `user-top-read user-read-recently-played user-library-read` (adding `streaming user-read-playback-state user-modify-playback-state` in Phase 2). A Last.fm API key is needed only from Phase 3.
