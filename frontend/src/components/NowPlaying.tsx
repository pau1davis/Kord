import { useState } from "react";
import type { Theory, TrackSummary } from "../api";
import type { Player } from "../player";

const RATES = [0.5, 0.75, 1];
const SKIP_SECONDS = 10;

/**
 * The song's identity and its transport in one card, the way a phone shows a
 * track you are playing: sleeve, title, artist, controls. Everything you need
 * to start the song sits in one place rather than scattered down the page.
 */
export function NowPlaying({
  track, theory, chordCount, player, playing, currentTime,
}: {
  track: TrackSummary;
  theory?: Theory;
  chordCount: number;
  player: Player | null;
  playing: boolean;
  currentTime: number;
}) {
  // Display-only: the source of truth is player.el.playbackRate. This exists so
  // the active pill updates on click even while paused, when currentTime is
  // not changing and nothing else would re-render this.
  const [selectedRate, setSelectedRate] = useState(player?.el.playbackRate ?? 1);

  return (
    <div className="nowcard">
      {track.image ? (
        <img className="sleeve" src={track.image} alt="" />
      ) : (
        <div className="sleeve no-art" aria-hidden="true" />
      )}

      <div className="nowmeta">
        <h2>{track.title}</h2>
        <p className="artist">{track.artist}</p>

        {theory && (
          <ul className="facts">
            <li>Key <b>{theory.key}</b></li>
            <li>Tempo <b>{Math.round(theory.tempo)}</b> BPM</li>
            <li><b>{chordCount}</b> chords</li>
          </ul>
        )}

        {player && (
          <div className="transport">
            <button
              className="skip"
              title={`Back ${SKIP_SECONDS} seconds`}
              onClick={() => player.seek(currentTime - SKIP_SECONDS)}
            >
              ↺{SKIP_SECONDS}
            </button>
            <button className="playbtn" onClick={() => player.toggle()}>
              {playing ? "Pause" : "Play"}
            </button>
            <button
              className="skip"
              title={`Forward ${SKIP_SECONDS} seconds`}
              onClick={() => player.seek(currentTime + SKIP_SECONDS)}
            >
              ↻{SKIP_SECONDS}
            </button>

            <div className="rates">
              {RATES.map((rate) => (
                <button
                  key={rate}
                  onClick={() => {
                    player.setRate(rate);
                    setSelectedRate(rate);
                  }}
                  className={selectedRate === rate ? "on" : undefined}
                >
                  {rate}×
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
