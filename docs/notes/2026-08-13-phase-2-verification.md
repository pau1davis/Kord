# Phase 2 verification — 2026-08-13

Verified against a fresh end-to-end analysis of **Pantera — Mouth for War**
(`6rkeaQRCWZxwkjhyqgxjXi`), the song the plan nominates as the stress test.

## 1. Test suites

| Suite | Result |
|---|---|
| `pytest` | 231 passed |
| `vitest` | 20 passed (2 files) |
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

§4 below is quantitative evidence bearing on 4; it is not a substitute for
listening. §6 is a concrete risk bearing on 1–3.

## 4. Finding: `collapseShortSegments` does not prevent the strobe

This is the substantive defect found. Running the real chart through the
same 0.4 s collapse the hero display uses:

```
input                171 segments, min 0.092s, 45 under 0.4s
after collapse       159 segments, min 0.092s, 24 still under 0.4s
worst-case rate      652 chord changes per minute
```

The function only merges *consecutive runs* of short chords. A single short
chord sandwiched between two long ones is flushed through unchanged, because
`flush()` emits whatever is in the run regardless of whether the run reached
`minSeconds`. Twenty-four segments therefore survive below the threshold, the
shortest at 92 ms — which is precisely the unreadable flicker the function
exists to remove.

The fix is a design decision rather than a typo, which is why it is recorded
here rather than patched: a lone 92 ms chord has to go *somewhere*, and the
options (absorb into the previous segment, absorb into whichever neighbour is
longer, or drop it from the display entirely) differ musically. The chord
sheet shows every change either way, so this only affects the hero display.

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
- **`/api/auth/status` reports `false` when only the access token has
  expired**, even though a stored refresh token would succeed — the refresh
  happens lazily inside `require_token()`. The UI can therefore show a
  "connect your account" state for a session that is actually fine. Phase 1
  behaviour, not introduced here.
- The chart ends at 233.5 s against a 237.3 s track; the tail is trimmed
  silence/outro.
