import type { ChartEntry } from "../api";

function timecode(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Every chord, collapsed behind a disclosure. The hero display shows one at a time. */
export function ChordSheet({
  entries, onSeek,
}: {
  entries: ChartEntry[];
  onSeek: (t: number) => void;
}) {
  return (
    <details className="chordsheet">
      <summary>All {entries.length} chords</summary>
      <ul className="chart">
        {entries.map((entry, index) => (
          <li
            key={`${entry.start_s}-${index}`}
            className={entry.uncertain ? "chord uncertain" : "chord"}
            style={{ ["--hue" as string]: entry.hue }}
            title={entry.uncertain ? "Low confidence — check this one by ear" : undefined}
          >
            <button onClick={() => onSeek(entry.start_s)}>
              <span className="time">{timecode(entry.start_s)}</span>
              <span className="name">{entry.label}</span>
              <span className="roman">{entry.roman}</span>
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}
