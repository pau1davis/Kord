const WINDOW_SECONDS = 4;

/** Beat marks around the playhead, so it is visible whether a change lands on the beat. */
export function BeatStrip({ beats, now }: { beats: number[]; now: number }) {
  const visible = beats.filter((t) => t > now - WINDOW_SECONDS / 2 && t < now + WINDOW_SECONDS / 2);
  return (
    <div className="beatstrip" aria-hidden="true">
      {visible.map((t) => (
        <span
          key={t}
          className="beat"
          style={{ left: `${((t - (now - WINDOW_SECONDS / 2)) / WINDOW_SECONDS) * 100}%` }}
        />
      ))}
      <span className="playhead" />
    </div>
  );
}
