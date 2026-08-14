import { useMemo } from "react";
import type { ChartEntry } from "../api";
import { chartTime, collapseShortSegments, findChordIndexAt } from "../chart";
import { BeatStrip } from "./BeatStrip";

const HERO_MIN_SECONDS = 0.4;

export function PlayAlong({
  chart, syncOffsetMs, beats, currentTime,
}: {
  chart: ChartEntry[];
  syncOffsetMs: number;
  beats: number[];
  currentTime: number;
}) {
  // The playhead is owned by App and passed down, so the song map and the hero
  // chord advance from the same frame. Owning it here would leave SongMap frozen.
  const display = useMemo(
    () => collapseShortSegments(chart, HERO_MIN_SECONDS), [chart]);

  const now = chartTime(currentTime, syncOffsetMs);
  const index = findChordIndexAt(display, now);
  const current = index >= 0 ? display[index] : null;
  const next = index >= 0 ? display[index + 1] : display[0];
  const until = next ? Math.max(0, next.start_s - now) : null;

  return (
    <section className="playalong">
      <div className="hero" style={{ ["--hue" as string]: current?.hue ?? 220 }}>
        <span className="hero-chord">{current ? current.label : "—"}</span>
        <span className="roman">{current?.roman ?? ""}</span>
      </div>

      <div className="upnext">
        {next ? (
          <>
            <span className="lbl">next</span>
            <span className="name" style={{ ["--hue" as string]: next.hue }}>
              {next.label}
            </span>
            {until !== null && <span className="in">in {until.toFixed(1)}s</span>}
          </>
        ) : (
          <span className="lbl">end of song</span>
        )}
      </div>

      <BeatStrip beats={beats} now={now} />

    </section>
  );
}
