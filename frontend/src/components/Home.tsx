import { useEffect, useState } from "react";
import {
  analyzeTop, getTaste, getTopTracks,
  type Taste, type TrackSummary,
} from "../api";
import { MoodRing } from "./MoodRing";

/** Art orbits on a circle; index decides where each one sits on it. */
function orbitStyle(index: number, count: number): React.CSSProperties {
  const angle = (index / Math.max(1, count)) * 360;
  // Two rings so a couple of dozen covers don't crowd a single circle.
  const radius = index % 2 === 0 ? 38 : 26;
  return {
    ["--angle" as string]: `${angle}deg`,
    ["--radius" as string]: `${radius}%`,
    ["--delay" as string]: `${(index % 7) * -4}s`,
  };
}

export function Home({ onPick }: { onPick: (track: TrackSummary) => void }) {
  const [tracks, setTracks] = useState<TrackSummary[]>([]);
  const [taste, setTaste] = useState<Taste | null>(null);
  const [failed, setFailed] = useState(false);

  // Art first: this needs metadata only, so it is on screen immediately.
  useEffect(() => {
    let live = true;
    getTopTracks()
      .then((list) => { if (live) setTracks(list); })
      .catch(() => { if (live) setFailed(true); });
    // Queue whatever has not been analysed. Safe to call repeatedly.
    analyzeTop().catch(() => {});
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

  if (failed) {
    return (
      <div className="empty">
        <h2>Connect your Spotify account.</h2>
        <p>Kord builds this page from the music you actually listen to.</p>
      </div>
    );
  }

  return (
    <MoodRing stops={taste?.palette ?? []}>
      <div className="home">
        <div className="orbit" aria-hidden="true">
          {tracks.slice(0, 24).map((track, index) => (
            track.image ? (
              <img
                key={track.id}
                src={track.image}
                alt=""
                style={orbitStyle(index, Math.min(tracks.length, 24))}
              />
            ) : null
          ))}
        </div>

        <div className="home-copy">
          <p className="eyebrow">Your music</p>
          <h2>What you've been listening to.</h2>
          {taste && taste.analyzed < taste.total && (
            <p className="hint">
              Working out the harmony — {taste.analyzed} of {taste.total} done.
              The colour fills in as it goes.
            </p>
          )}
        </div>

        <ul className="toplist">
          {tracks.slice(0, 12).map((track) => (
            <li key={track.id}>
              <button onClick={() => onPick(track)}>
                <span className="title">{track.title}</span>
                <span className="artist">{track.artist}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </MoodRing>
  );
}
