import type { ChartEntry } from "../api";

function timecode(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

export function ChordChart({ entries }: { entries: ChartEntry[] }) {
  if (entries.length === 0) {
    return <p className="detail">No chords came through on this one.</p>;
  }

  return (
    <ul className="chart">
      {entries.map((entry, index) => (
        <li
          key={`${entry.start_s}-${index}`}
          className={entry.uncertain ? "chord uncertain" : "chord"}
          style={{ ["--hue" as string]: entry.hue }}
          title={entry.uncertain ? "Low confidence — check this one by ear" : undefined}
        >
          <span className="time">{timecode(entry.start_s)}</span>
          <span className="name">{entry.label}</span>
          <span className="roman">{entry.roman}</span>
        </li>
      ))}
    </ul>
  );
}
