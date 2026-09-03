# Kord without Spotify

**Status:** design, awaiting review
**Date:** 2026-08-18

## 1. What this is for

Kord currently refuses to do anything without a Spotify account. Search,
opening a song, and therefore every feature behind it — chords, stems, tab —
all sit behind an OAuth flow that needs a developer account, a client ID and a
browser round trip.

The immediate reason to change that is a person: the author's brother has a show
to play and wants to hear the guitar part on its own. He has no reason to care
about Spotify, and asking a non-technical player to register a developer
application before they can isolate a guitar is absurd.

The general reason is better. Spotify is used for exactly two things in the core
flow — finding a song by name, and knowing its duration — and neither requires
it. Apple's iTunes Search API answers both with no account, no key and no OAuth:

```
GET https://itunes.apple.com/search?term=pantera+mouth+for+war&entity=song

Pantera   Mouth for War                236960ms  artwork
Pantera   Mouth for War (Live from…)   241920ms  artwork
```

`trackTimeMillis` is the field that matters most. Duration is what Kord uses to
pick the right upload and reject live takes, so replacing Spotify costs nothing
in analysis quality.

### Goals

1. Search, play and analyse a song with **no account of any kind**.
2. Spotify becomes an optional sign-in that adds the personal home screen and
   nothing else.
3. Import a local audio file, for music that is not findable or not released.
4. Lose nothing already in the library: 64 tracks and 113 analyses stay valid.

### Non-goals

- **Offline operation.** Looking a song up and fetching its audio both need the
  network. What changes is that Kord is not *hosted* — it runs on your machine
  — and that it needs no credentials.
- **Replacing YouTube** as the audio source. Only metadata moves.
- **Packaging.** The Mac bundle is a separate project and depends on this one
  landing first (§10).
- **A music library manager.** Imported files are analysed, not catalogued.

## 2. What actually depends on Spotify

Nine `require_token()` calls, and only two of them block ordinary use:

| Call site | Purpose | After |
|---|---|---|
| `search_tracks` | find a song by name | **moves to the metadata seam** |
| `get_track` | title, artist, duration, art | **moves to the metadata seam** |
| `top_tracks` ×3 | the taste home screen | stays behind sign-in |
| `recently_played` | "just played on Spotify" shelf | stays behind sign-in |
| `auth_status` | is the session usable | unchanged |

`/api/me/library` already reads only local data and needs no token today.

So the refactor is narrow. The risk is not in the count of call sites but in
track identity (§4).

## 3. The metadata seam

A protocol mirroring the existing `AudioSource` seam, which has already proved
the pattern — `youtube.py` is the only module importing yt-dlp, enforced by a
test rather than by discipline.

```python
class MetadataSource(Protocol):
    """Where song facts come from. Never audio — that is AudioSource."""

    async def search(self, query: str, limit: int = 20) -> list[TrackFacts]: ...

    async def get(self, track_id: str) -> TrackFacts: ...
```

```python
@dataclass(frozen=True)
class TrackFacts:
    id: str            # namespaced, see §4
    title: str
    artist: str
    album: str | None
    duration_ms: int
    image: str | None
```

Two implementations:

- **`ItunesMetadata`** — the default. No auth. Public endpoint, no key.
- **`SpotifyMetadata`** — wraps the existing client, used when signed in.

Chosen per request rather than at startup: if a session exists, Spotify answers
(its catalogue is better and it is what the user's existing IDs refer to);
otherwise iTunes does. One line, and it means signing in silently upgrades
search rather than unlocking it.

### 3.1 What iTunes gets wrong, and why it does not matter

Its search ranks poorly compared to Spotify's and returns duplicates and live
versions high in the list. That is acceptable because the results are *shown to
the player, who picks one* — the same as today. Kord's existing title filter
(`title_match.py`) already rejects live takes at the audio-selection stage,
which is where a mistake would actually cost something.

Rate limits are undocumented but real (roughly 20 calls/minute). Search is
user-initiated and infrequent, so this is not the throttle case that YouTube
needed; a 429 surfaces as an ordinary search error.

## 4. Track identity — the part that can break the library

Every row in `track`, `analysis`, `job`, `stem_job`, `tab_job` and
`tempo_override` is keyed on a column called `spotify_id` holding a bare Spotify
ID. Adding a second provider needs a namespace, and getting this wrong
re-analyses 64 songs or orphans their stems.

**Rule:** an ID with no `:` is a Spotify ID. New IDs are prefixed.

```
3VqHuw0wFlIHcIPWkhIbdQ     existing rows, unchanged forever
itunes:1440857781          from the iTunes catalogue
file:a3f29c81...           an imported file, ID is its content hash
```

No migration and no data touched. The column keeps its name — renaming it
across six tables and every query is churn that buys nothing, and the docstring
can say what it now holds. `provider_of(track_id)` is one pure function with
tests, and it is the only place that knows the convention.

A content hash for imported files means importing the same file twice finds the
existing analysis instead of redoing three minutes of work.

## 5. Auth becomes optional

`require_token()` keeps its behaviour but is called from fewer places. The
frontend stops treating 401 as fatal:

- **Search** never 401s. Signed out, it queries iTunes.
- **The home screen** currently *is* the Spotify taste ring. Signed out it
  shows what the app knows locally: recently opened songs (`db.recently_opened`
  exists and is currently used only to pick a single track elsewhere, so the
  screen is new but the query is not), the library summary that
  `/api/me/library` already returns, and a prompt to search. Signing in adds the
  orbiting art and the taste colours on top.
- **A "Connect Spotify" affordance** stays available but is never a wall.

The rule: nothing that works on local data may require a token.

## 6. Importing a file

`POST /api/import` accepts one audio file, hashes it, stores it in the audio
store under `file:<hash>`, writes a `track` row with metadata read from tags
(falling back to the filename), and enqueues analysis. From there it is an
ordinary song — stems, chords, tab and the mixer all work unchanged, because
they were never Spotify-specific.

This is the path that makes Kord work for unreleased material, live recordings
of your own band, and anything the catalogues do not have. It is secondary to
search by design: most people have a song title in mind, not a file.

`AnalysisPipeline.run` gains an optional `audio_path`. When given, it skips the
search and download entirely and analyses that file:

```python
def run(self, track_id, artist, title, duration_ms,
        audio_path: Path | None = None) -> Analysis: ...
```

That is a smaller change than a new `AudioSource`, and more honest: an imported
file was never *found*, so making a fake source that "searches" for a file we
already hold would be ceremony. `speed_adjusted` cannot apply and `time_scale`
stays 1.0, because there is no upload to be mismatched against.

## 7. Endpoints

| Method | Path | Auth | Change |
|---|---|---|---|
| `GET` | `/api/search?q=` | none | provider chosen per request |
| `GET` | `/api/track/{id}` | none | provider chosen per request |
| `POST` | `/api/import` | none | **new** |
| `GET` | `/api/me/*` | required | unchanged |
| `GET` | `/api/auth/*` | none | unchanged |

Everything under `/api/track/{id}/` — audio, stems, tab, tempo — is untouched
and already needs no token.

## 8. Testing

- **`provider_of`** — table-driven over bare, prefixed and malformed IDs.
  Includes the case the library depends on: a bare ID is Spotify, forever.
- **`ItunesMetadata`** — against recorded fixtures, not the live API, so the
  suite stays offline and deterministic. One test asserts the mapping of
  `trackTimeMillis` to `duration_ms`, because a duration in the wrong unit would
  silently poison candidate selection rather than fail.
- **Provider choice** — signed out uses iTunes, signed in uses Spotify, and the
  choice is per request rather than cached at startup.
- **Search without a token returns 200**, which is the whole point and would
  otherwise regress silently.
- **Import** — the same file twice yields one track and one analysis.
- **The existing suite must stay green**: 447 tests, including everything that
  currently assumes a signed-in client.

## 9. What this costs your own copy

Nothing is removed. Signed in, the app behaves exactly as it does now, except
search may answer from Spotify or iTunes depending on session state. The 64
existing tracks keep their bare IDs and never re-analyse.

The one visible change is that the signed-out home screen now exists, where
before it was a wall.

## 10. Build order

1. `provider_of` and the ID convention — everything else depends on it.
2. The `MetadataSource` seam and `ItunesMetadata`.
3. Wiring `search` and `get_track` to the seam; auth becomes optional.
4. The signed-out home screen.
5. File import.

Then, as a separate project: the Mac bundle.

## 11. Open questions

- Whether the signed-out home screen should offer a "try one of these" list of
  well-known songs to get a new user started, or just a search box. Decided
  during implementation by looking at how empty the screen feels; it changes
  no interfaces.
