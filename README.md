# Kord

See what a song is made of. Connect Spotify, search anything, and Kord works out
the chords, the key, and the scales that fit over it — then colours the page by
the harmony you're listening to.

Personal tool, runs entirely on your machine.

## Why it works the way it does

Spotify deprecated `audio-features`, `audio-analysis`, `recommendations`,
`related-artists` and 30-second `preview_url`s for all new apps on 2024-11-27,
and Web Playback SDK audio is DRM-protected. **Spotify can supply no audio and no
music theory whatsoever.**

So Kord splits in two: Spotify handles identity, search and metadata, while a
local pipeline fetches audio separately, analyses it once, caches the result, and
deletes the audio. Full reasoning in
[`docs/specs/2026-08-11-kord-design.md`](docs/specs/2026-08-11-kord-design.md).

## Setup

```bash
brew install ffmpeg yt-dlp
./setup.sh
```

`setup.sh` checks prerequisites, builds the Python 3.11 virtualenv, installs
everything, fetches the 12 MB chord model, and runs the test suite.

Then create a Spotify app at <https://developer.spotify.com/dashboard>, register
`http://127.0.0.1:8000/api/auth/callback` as a redirect URI, and paste the
**Client ID** into `.env`. There is no client secret — Kord uses PKCE.

No Spotify Premium required. Nothing plays audio in Phase 1.

> Run `./setup.sh` rather than pasting the pip command by hand. The extras
> syntax `.[dev,btc]` is a glob pattern in zsh, so a mis-quoted copy-paste
> aborts the whole command chain with a single easily-missed line.

Without the model weights Kord still runs, falling back to a chroma baseline that
recognises major and minor triads only. The worker log says which engine is active.

## Running

```bash
./run.sh
```

Starts the API, the analysis worker and the UI together; Ctrl-C stops all three.
Open the URL it prints and connect Spotify at <http://127.0.0.1:8000/api/auth/login>.

To run them separately instead:

```bash
.venv/bin/uvicorn kord.app:build_app --factory --port 8000 --app-dir backend
.venv/bin/python -m kord.queue
cd frontend && npm run dev
```

## How a lookup goes

1. Search hits Spotify; you pick a track.
2. Cache hit renders instantly. Otherwise a job is queued.
3. The worker finds audio, **matching track length within 2%** so it doesn't
   analyse a live cut or a cover, then decodes, analyses, stores the result, and
   deletes the audio.
4. Chart, theory and mood field render.

Roughly 6 seconds per song on an M1, using about 500 MB. Analyses are cached
forever and keyed by engine version, so improving the analyser invalidates stale
results rather than mixing them.

## Reading the output

- **Dashed, faded chords** are low confidence — check those by ear. Kord shows
  uncertainty rather than asserting a confident guess.
- **A `?` after the key** means the two key estimators disagreed.
- **Colour is chord quality**: red power chords, gold major, blue minor, purple
  diminished or augmented, teal suspended, amber dominant 7ths. A song's palette is
  weighted by how long each quality sounds.

## Tests

```bash
pytest -q          # never touches the network
```

Audio for tests is synthesised in numpy, so there are no fixture files and no
dependency on YouTube or Spotify being reachable.

## Layout

```
backend/kord/
  theory/      chord vocabulary, hues, roman numerals, scales   (pure, no I/O)
  audio/       source adapters, duration validation, decoding
  analysis/    recognizers, timbre, key, beats, pipeline
  spotify.py   OAuth PKCE and search
  queue.py     worker process
  app.py       HTTP API
frontend/src/  React UI
```

`yt-dlp` is imported in exactly one file, `backend/kord/audio/youtube.py`, and a
test enforces that. Swapping audio providers means writing one adapter.

## Status

Phase 2. You can play a song back and follow along with it.

Playback comes from the audio Kord analysed, not from Spotify. That is what
makes the sync exact: the chord timestamps were measured against this exact
file, so there is nothing to calibrate and nothing to drift. Spotify is used
for search and metadata only — no playback SDK, no premium requirement.

What works:

- **Play along** — a hero chord that changes with the music, what is coming
  next, and a beat strip for context.
- **Slow down** to 0.75× or 0.5× without changing pitch.
- **Loop a section** — drag across the song map to pick a range, click a
  block to jump to it.
- **The full chord sheet** is still there, collapsed behind a disclosure, and
  every row seeks.

Analysed audio is kept on disk under `~/.kord/audio` so a song is only ever
downloaded once. The store is capped by `KORD_AUDIO_CAP_GB` (default 2) and
evicts least-recently-used files when it would go over.

Known rough edges are recorded in
`docs/notes/2026-08-13-phase-2-verification.md` — most notably
that stored audio is WebM, which Safari may refuse to play, and that section
detection is coarse enough to be navigation rather than a verse/chorus map.

Listening-history mood ring, recommendations, chart export and bass tablature
are later phases — see the spec.
