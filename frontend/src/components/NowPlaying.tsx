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
/** Only ever halve, leave, or double — a tempo error you can hear is an octave. */
const FACTORS = [0.5, 1, 2] as const;

function halveFactor(current: number): number {
  return FACTORS[Math.max(0, FACTORS.indexOf(current as 0.5 | 1 | 2) - 1)];
}

function doubleFactor(current: number): number {
  const i = FACTORS.indexOf(current as 0.5 | 1 | 2);
  return FACTORS[Math.min(FACTORS.length - 1, i + 1)];
}

export function NowPlaying({
  track, theory, chordCount, player, playing, currentTime,
  tempoFactor = 1, onTempoFactor,
}: {
  track: TrackSummary;
  theory?: Theory;
  chordCount: number;
  player: Player | null;
  playing: boolean;
  currentTime: number;
  tempoFactor?: number;
  onTempoFactor?: (factor: number) => void;
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
            <li className="tempo">
              Tempo <b>{Math.round(theory.tempo)}</b> BPM
              {onTempoFactor && (
                <span className="tempofix">
                  {/* Detecting half-time from audio was measured and does not
                      work: most rock plays the eighths, so nothing separates a
                      missed beat from a subdivision. You know the song. */}
                  <button
                    title={`Half time — ${Math.round(theory.tempo / 2)} BPM`}
                    onClick={() => onTempoFactor(halveFactor(tempoFactor))}
                    disabled={halveFactor(tempoFactor) === tempoFactor}
                  >÷2</button>
                  <button
                    title={`Double time — ${Math.round(theory.tempo * 2)} BPM`}
                    onClick={() => onTempoFactor(doubleFactor(tempoFactor))}
                    disabled={doubleFactor(tempoFactor) === tempoFactor}
                  >×2</button>
                </span>
              )}
              {tempoFactor !== 1 && (
                <button
                  className="temporeset"
                  title="Back to the measured tempo"
                  onClick={() => onTempoFactor?.(1)}
                >corrected</button>
              )}
            </li>
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
