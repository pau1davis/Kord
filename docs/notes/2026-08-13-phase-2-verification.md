# Phase 2 verification — 2026-08-13

Verified against a fresh end-to-end analysis of **Pantera — Mouth for War**
(`6rkeaQRCWZxwkjhyqgxjXi`), the song the plan nominates as the stress test.

## 1. Test suites

| Suite | Result |
|---|---|
| `pytest` | 231 passed |
| `vitest` | 24 passed (2 files) |
| `npm run build` | clean, `tsc -b` included |

The backend count rose from 226 to 231: five new tests cover the download
fallback described in §5.

## 2. End-to-end analysis

Stack restarted via `./run.sh`; song re-analysed through the API.

- Audio retained: `~/.kord/audio/6rkeaQRCWZxwkjhyqgxjXi.webm`, 3.74 MB.
  Store total after one song: **3.6 MB**. Nowhere near the 2 GB default cap,
  so eviction was not exercised by this run.
- `GET /api/track/{id}` reports `has_audio: true`, `sections` non-empty (8),
  `beats` non-empty (408), `sync_offset_ms: 511`, `time_scale: 1.0`,
  `flags: []`, key E major, tempo 103.4, 171 chords.
- `time_scale` is recorded but no longer applied to timestamps, as intended.

### Range requests

| Request | Status | Bytes |
|---|---|---|
| `Range: bytes=0-99` | 206 | 100 |
| `Range: bytes=1000000-1000999` | 206 | 1000 |
| no Range header | 200 | 3740154 |
| unknown track id | 404 | — |

Headers on the ranged response are correct: `accept-ranges: bytes`,
`content-range: bytes 0-99/3740154`, `content-length: 100`.

## 3. Checks that still need a human

I have no browser or audio output in this environment, so the four
by-ear/by-eye checks in the plan are **not** verified. They remain open:

1. Does the chart track the song with no adjustment?
2. Does 0.5× stay in the same key (`preservesPitch`)?
3. Does looping a section repeat cleanly?
4. Does the hero chord stay readable on a fast song?

§4 below is quantitative evidence bearing on check 4 — the segment durations
feeding the display are now provably readable — but whether it *reads* well at
speed still needs eyes on it. §6 is a concrete risk bearing on 1–3.

## 4. Fixed: `collapseShortSegments` did not prevent the strobe

This was the substantive defect found. The function only merged *consecutive
runs* of short chords: a single short chord sandwiched between two long ones
was flushed through unchanged, because `flush()` emitted whatever was in the
run regardless of whether the run had reached `minSeconds`. The shortest
survivor was 92 ms — precisely the unreadable flicker the function exists to
remove. The first unit test had encoded the bug, asserting a 0.2 s output
segment under a 0.4 s minimum.

`absorbShortSegments` now runs as a second pass: any segment still under the
minimum is merged into whichever neighbour is longer, ties going to the
previous segment (which reads as holding the chord you are already playing
through the blip). Merging only lengthens a segment and removes one, so it
terminates, and it stops at a single segment — a song shorter than the
minimum has nowhere left to merge to.

The invariant is now: **no output segment is shorter than `minSeconds` unless
the whole song is.** Measured against this track's real chart at 0.4 s:

| | before | after |
|---|---|---|
| segments | 159 | 135 |
| under 0.4 s | 24 | **0** |
| shortest | 0.092 s | 0.462 s |
| worst-case rate | 652/min | 130/min |
| coverage | 0.00→233.52 | 0.00→233.52 |

Coverage is unchanged, so nothing is dropped from the timeline. The chord
sheet still shows all 171 changes; this only affects the hero display.

## 5. Finding: a single failed download killed the whole song

First attempt failed outright:

```
job 6  failed  DownloadError: unable to download video data: HTTP Error 403: Forbidden
```

`select_candidate` returned exactly one candidate and the pipeline had no
fallback, so one bad candidate failed the song. For "Mouth for War" the
closest duration match (238.0 s vs Spotify's 237.3 s) is the official music
video; the `tv` player client reports it as DRM protected, while two
re-uploads at 237.0 s download fine.

Changed: `rank_candidates` now returns every acceptable candidate, clean tier
first, and the pipeline tries each until one downloads
(`AnalysisPipeline._download_best`). `select_candidate` is kept as a thin
wrapper over the top-ranked result, so existing callers and tests are
unaffected.

**Honest caveat:** the retry that succeeded used the *primary* candidate
(`source_url` recorded as `a3JSbOt7CLo`, the official video), so the 403 was
intermittent rather than a permanent DRM block, and the new fallback path is
not what unblocked this particular run. It is covered by tests and protects
against the permanent case, but it has not yet fired in production.

yt-dlp was checked for staleness and is already current (2026.07.04, the
latest on PyPI), so the 403 was not a version problem.

## 6. Finding: stored audio is WebM/Opus

The retained file is whatever the source served — here `.webm` (Opus, format
251) — and the endpoint returns `content-type: video/webm`. Chrome and
Firefox play this in an `<audio>` element; **Safari's WebM support is
limited**, so playback may simply fail there. Worth confirming on whichever
browser is actually used before trusting checks 1–3 above. Two mitigations
exist if it bites: serve `audio/webm` instead of `video/webm`, or constrain
the download format to m4a.

## 7. Smaller observations

- **25 gaps/overlaps** between adjacent chart segments. `findChordAt` returns
  null inside a gap, so the hero briefly shows `—`.
- **Section detection is coarse.** Eight sections, labelled only A/B, with
  lengths `[0.1, 36.8, 50.4, 11.6, 51.0, 85.7, 0.5, 1.1]`. The three slivers
  under 1.2 s will render as near-invisible slivers in the song map, and one
  85.7 s block covers a third of the song. Usable for navigation, but not the
  verse/chorus map the UI implies.
- **Fixed: the session died after an hour of uptime.** Recorded here
  originally as "`/api/auth/status` reports `false` when the access token has
  expired", which had it backwards. The real failure is worse and is described
  in §8.
- The chart ends at 233.5 s against a 237.3 s track; the tail is trimmed
  silence/outro.

## 8. Fixed: every search 401d after an hour of uptime

Found by using the app rather than testing it: the UI showed "Connect your
Spotify account, then search again." while `/api/auth/status` insisted the
account *was* connected.

The two signals disagreed, which located it:

```
GET /api/auth/status  ->  {"authenticated": true}
GET /api/search?q=..  ->  401 {"detail":"Missing/invalid/expired access token",
                               "spotify_status":401}
```

The 401 came from Spotify, not from Kord — so Kord was confidently sending a
token Spotify had already expired. `require_token()` opened with:

```python
if app.state.access_token:
    return app.state.access_token
```

`db.load_session` computes expiry correctly and is the single source of truth,
but the in-memory cache bypassed it entirely. The cache is populated at startup
while the token is valid, so the refresh branch underneath was unreachable for
as long as the process lived. Once the hour was up, every Spotify call failed
until the server happened to restart — and a restart re-read the session,
found it expired and refreshed cleanly, which is exactly why this never showed
up during the earlier verification runs.

**Fixed** by having `require_token()` consult `load_session()` on every call
and treat `app.state.access_token` as nothing more than a cache.
`/api/auth/status` now answers "can we actually call Spotify?" — true when the
token is live *or* a refresh token exists, false otherwise — instead of "is a
token cached?", which is what let the UI claim connected while stranded.

Verified against the running server, with no restart: forcing `expires_at`
into the past mid-flight, the next search refreshed the session silently and
returned results. Three tests cover it, and the `client` fixture now stores a
real session rather than assigning a bare token, since expiry is read from the
session on every call.
