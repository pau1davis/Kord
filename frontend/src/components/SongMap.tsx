import { useState } from "react";
import type { SongSection } from "../api";
import type { LoopRange } from "../chart";

export function SongMap({
  sections, now, loop, onSeek, onLoopChange,
}: {
  sections: SongSection[];
  now: number;
  loop: LoopRange | null;
  onSeek: (t: number) => void;
  onLoopChange: (loop: LoopRange | null) => void;
}) {
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  if (sections.length === 0) return null;

  const total = sections[sections.length - 1].end_s || 1;

  function selectRange(a: number, b: number) {
    const lo = Math.min(a, b);
    const hi = Math.max(a, b);
    onLoopChange({ start: sections[lo].start_s, end: sections[hi].end_s });
  }

  return (
    <div className="songmap">
      <div className="blocks">
        {sections.map((section, index) => {
          const inLoop = loop !== null
            && section.start_s >= loop.start - 1e-6
            && section.end_s <= loop.end + 1e-6;
          const isCurrent = now >= section.start_s && now < section.end_s;
          return (
            <button
              key={`${section.start_s}-${index}`}
              className={[
                "block",
                isCurrent ? "current" : "",
                inLoop ? "looped" : "",
              ].filter(Boolean).join(" ")}
              style={{ flexGrow: section.end_s - section.start_s }}
              title={`Section ${section.label} — click to jump, drag to loop`}
              onMouseDown={() => setDragFrom(index)}
              onMouseUp={() => {
                if (dragFrom === null || dragFrom === index) onSeek(section.start_s);
                else selectRange(dragFrom, index);
                setDragFrom(null);
              }}
            >
              <span>{section.label}</span>
            </button>
          );
        })}
        <span
          className="cursor"
          style={{ left: `${Math.min(100, Math.max(0, (now / total) * 100))}%` }}
        />
      </div>

      {loop && (
        <button className="clearloop" onClick={() => onLoopChange(null)}>
          Looping {loop.start.toFixed(0)}s – {loop.end.toFixed(0)}s · clear
        </button>
      )}
    </div>
  );
}
