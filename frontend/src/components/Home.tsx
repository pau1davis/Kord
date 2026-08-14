import { useEffect, useState } from "react";
import {
  analyzeTop, getTaste, getTopTracks,
  type Taste, type TrackSummary,
} from "../api";
import { MoodRing } from "./MoodRing";

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
  const [failed, setFailed] = useState(false);

  // Art first: this needs metadata only, so it is on screen immediately.
  useEffect(() => {
    let live = true;
    getTopTracks()
      .then((list) => { if (live) setTracks(list); })
      .catch(() => { if (live) setFailed(true); });
    // Queue whatever has not been analysed. Safe to call repeatedly, and it
    // retries anything that failed to download last time.
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

  const ring = tracks.slice(0, ON_THE_RING);

  return (
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
          <span className="strings" aria-hidden="true" />
          <p className="eyebrow">Your music</p>
          <h2>What you've been listening to.</h2>
          {taste && taste.analyzed < taste.total && (
            <p className="hint">
              Working out the harmony — {taste.analyzed} of {taste.total} done.
              The colour fills in as it goes.
            </p>
          )}
        </div>
      </div>
    </MoodRing>
  );
}
