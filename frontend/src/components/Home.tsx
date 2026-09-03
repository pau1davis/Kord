import { useEffect, useState } from "react";
import {
  analyzeTop, ApiError, getLibrary, getRecent, getRecentlyOpened, getTaste,
  getTopTracks, type Library, type Taste, type TrackSummary,
} from "../api";
import { homeMode } from "../home";
import { MoodRing } from "./MoodRing";
import { Workbench } from "./Workbench";

/**
 * How many sleeves ride the ring.
 *
 * Eight, not twelve: at the radius that fits a laptop viewport, twelve cards
 * are closer together than they are wide, so they overlap each other and run
 * over the title. Circumference divided by count has to beat card width.
 */
const ON_THE_RING = 8;

/**
 * Place one sleeve on the circle.
 *
 * The radius is a length, not a percentage: a percentage in `translate`
 * resolves against the element's own box, which would bunch every sleeve a few
 * pixels from the centre rather than spreading them around the ring.
 */
function orbitStyle(index: number, count: number): React.CSSProperties {
  const angle = (index / Math.max(1, count)) * 360;
  return {
    ["--angle" as string]: `${angle}deg`,
    // One ring, wide enough that no sleeve reaches the copy at the centre.
    ["--radius" as string]: "clamp(185px, 34vmin, 340px)",
  };
}

export function Home({ onPick }: { onPick: (track: TrackSummary) => void }) {
  const [tracks, setTracks] = useState<TrackSummary[]>([]);
  const [taste, setTaste] = useState<Taste | null>(null);
  const [library, setLibrary] = useState<Library | null>(null);
  const [recent, setRecent] = useState<TrackSummary[]>([]);
  const [recentlyOpened, setRecentlyOpened] = useState<TrackSummary[]>([]);
  // Not a boolean: "your account isn't connected" and "the server didn't
  // answer" ask for different things from the reader, and telling someone to
  // reconnect Spotify when the backend is down sends them off to fix the one
  // thing that was never broken.
  const [problem, setProblem] = useState<ApiError | null>(null);

  // Art first: this needs metadata only, so it is on screen immediately.
  useEffect(() => {
    let live = true;
    getTopTracks()
      .then((list) => { if (live) setTracks(list); })
      .catch((e) => {
        if (live) setProblem(e instanceof ApiError ? e : new ApiError(0, String(e)));
      });
    // Queue whatever has not been analysed. Safe to call repeatedly, and it
    // retries anything that failed to download last time.
    analyzeTop().catch(() => {});
    // Local state, so it renders even if Spotify is unreachable.
    getLibrary().then((l) => { if (live) setLibrary(l); }).catch(() => {});
    getRecent().then((r) => { if (live) setRecent(r); }).catch(() => {});
    getRecentlyOpened()
      .then((r) => { if (live) setRecentlyOpened(r); })
      .catch(() => {});
    return () => { live = false; };
  }, []);

  // Colour arrives as songs finish analysing, so keep asking while it fills in.
  useEffect(() => {
    let live = true;
    let timer: number | undefined;
    async function poll() {
      try {
        const next = await getTaste();
        if (!live) return;
        setTaste(next);
        if (next.analyzed < next.total) timer = window.setTimeout(poll, 15000);
      } catch {
        if (live) timer = window.setTimeout(poll, 30000);
      }
    }
    poll();
    return () => { live = false; window.clearTimeout(timer); };
  }, []);

  const mode = homeMode(tracks.length > 0, problem);

  if (mode === "error") {
    return (
      <div className="empty">
        <h2>Kord couldn't load your music.</h2>
        <p>{problem?.message}</p>
      </div>
    );
  }

  if (mode === "local") {
    return (
      <div className="empty">
        <h2>Search for a song.</h2>
        <p>
          Type a song into the box above and Kord will find it, work out the
          chords, and split it into parts you can solo.
        </p>
        {library && library.analyzed > 0 && (
          <p className="hint">
            {library.analyzed} songs analysed so far.
          </p>
        )}
        {recentlyOpened.length > 0 && (
          <>
            <p className="shelf-label">Recently opened</p>
            <ul className="shelf-list">
              {recentlyOpened.map((track) => (
                <li key={track.id}>
                  <button onClick={() => onPick(track)}>
                    <span className="title">{track.title}</span>
                    <span className="artist">{track.artist}</span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
        <p className="hint">
          <a href="/api/auth/login">Connect Spotify</a> to see a home screen
          built from what you listen to. Everything else works without it.
        </p>
      </div>
    );
  }

  const ring = tracks.slice(0, ON_THE_RING);

  return (
    <>
      <MoodRing stops={taste?.palette ?? []}>
      <div className="home">
        <div className="orbit">
          {ring.map((track, index) => (
            <div
              key={track.id}
              className="orbit-item"
              style={orbitStyle(index, ring.length)}
            >
              <button className="sleevecard" onClick={() => onPick(track)}>
                {track.image ? (
                  <img src={track.image} alt="" />
                ) : (
                  <span className="no-art" aria-hidden="true" />
                )}
                <span className="text">
                  <span className="title">{track.title}</span>
                  <span className="artist">{track.artist}</span>
                </span>
              </button>
            </div>
          ))}
        </div>

        <div className="home-copy">
          <Workbench library={library} onResume={onPick} />
          {taste && taste.analyzed < taste.total && (
            <p className="hint">
              Working out the harmony — {taste.analyzed} of {taste.total} done.
            </p>
          )}
        </div>
      </div>
      </MoodRing>

      {recent.length > 0 && (
        <section className="shelf">
          <p className="shelf-label">Just played on Spotify</p>
          <ul>
            {recent.slice(0, 8).map((track) => (
              <li key={track.id}>
                <button onClick={() => onPick(track)}>
                  {track.image ? (
                    <img src={track.image} alt="" />
                  ) : (
                    <span className="no-art" aria-hidden="true" />
                  )}
                  <span className="title">{track.title}</span>
                  <span className="artist">{track.artist}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
