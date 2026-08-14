# Stem separation verification — 2026-08-14

Backend only. The Web Audio mixer UI is a separate plan; this verifies that
stems can be requested, produced, stored and served.

Song: Marvin Gaye — Mercy Mercy Me (`3IDc87lrpEHWFBASmgTgFV`), 193 s, retained
as m4a by the Part 0 work.

## Result

Requested 10:53:58, files written 10:55 — **about 1.5 minutes**, consistent
with the 2.0 min/4-min-song CPU benchmark the plan was built on.

```
{"status":"done","error":null,
 "available":["drums","bass","other","vocals","guitar","piano"]}
```

All six stems produced, including the explicit `guitar` stem that motivated
choosing `htdemucs_6s` over the default model.

## Disk

21 MB for six stems, roughly 3.1–3.3 MB each. The plan predicted ~25 MB and
the spec had originally estimated 100–200 MB; encoding to m4a rather than
writing Demucs' raw WAV output is the difference. WAV would have been ~254 MB
for a song of this length.

## Serving

```
GET /api/track/{id}/stems/guitar -> 200, content-type: audio/mp4, 3137624 bytes
GET /api/track/{id}/stems/trombone -> 404
```

## Objective separation check

Not a substitute for listening, but it rules out the failure modes that would
be embarrassing to miss — silent stems, or six copies of the same mix.

| stem | RMS | peak | spectral centroid |
|---|---|---|---|
| bass | 0.058 | 0.352 | **200 Hz** |
| drums | 0.086 | 0.780 | 2078 Hz |
| guitar | 0.020 | 0.191 | 1652 Hz |
| other | 0.030 | 0.254 | 770 Hz |
| piano | 0.017 | 0.299 | 1259 Hz |
| vocals | 0.085 | 0.860 | 2162 Hz |

Every stem carries signal — none is silent. No pair of stems correlates above
|r| = 0.3, so these are genuinely different signals rather than duplicates.
The centroids are musically sensible, with bass by far the lowest at 200 Hz.

## Still needs a human

Whether each stem *sounds* like its instrument, and how much bleed there is.
Objective measurements cannot answer that.

```bash
open ~/.kord/stems/3IDc87lrpEHWFBASmgTgFV/guitar.m4a
```

Bleed is expected and acceptable — stems are a practice aid, not a master.
What would matter is a stem that is obviously the wrong instrument.

## Notes

- `librosa` logs `PySoundFile failed. Trying audioread instead.` when loading
  m4a. Harmless — it falls back and decodes correctly — but it is a deprecated
  path in librosa 0.11 and will need attention before librosa 1.0.
- The model loads lazily, so the analysis worker pays nothing for Demucs until
  a stem job is actually claimed.
- Not yet exercised: stem separation running concurrently with an analysis job.
  The worker drains analysis first and stems second within one loop, so they
  cannot overlap in a single worker — separation will delay a queued analysis
  by up to one song's separation time. Acceptable for a single-user tool, but
  worth knowing if the taste home screen ever batch-analyses 50 tracks while a
  stem job is running.
