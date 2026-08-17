import { useEffect, useRef, useState } from "react";
import { getStems, requestStems, type StemState } from "../api";
import { createStemPlayer, type StemPlayer } from "../stemPlayer";
import { isSeparating } from "../stems";

function timecode(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function StemMixer({
  trackId, onActiveChange,
}: {
  trackId: string;
  onActiveChange: (active: boolean) => void;
}) {
  const [state, setState] = useState<StemState>("none");
  const [available, setAvailable] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [player, setPlayer] = useState<StemPlayer | null>(null);
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [playing, setPlaying] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const playerRef = useRef<StemPlayer | null>(null);

  // Poll while separation is running. Roughly 2 minutes for a 4 minute song.
  //
  // `separating` is a dependency so that pressing the button re-arms this: the
  // first fetch of an untouched song answers "none" and stops the loop, and
  // without that dependency nothing ever restarted it.
  const separating = isSeparating(state);
  useEffect(() => {
    let live = true;
    let timer: number | undefined;
    async function poll() {
      try {
        const s = await getStems(trackId);
        if (!live) return;
        setState(s.status);
        setAvailable(s.available);
        setError(s.error);
        setProgress(s.progress ?? 0);
        if (isSeparating(s.status)) timer = window.setTimeout(poll, 2000);
      } catch {
        if (live) timer = window.setTimeout(poll, 8000);
      }
    }
    poll();
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [trackId, separating]);

  // One player per song. Tearing it down closes its AudioContext, which is
  // what actually frees the decoded buffers.
  useEffect(() => {
    return () => {
      playerRef.current?.destroy();
      playerRef.current = null;
      setPlayer(null);
      setPlaying(false);
      setElapsed(0);
      onActiveChange(false);
    };
  }, [trackId, onActiveChange]);

  useEffect(() => {
    player?.applyGains(enabled);
  }, [player, enabled]);

  // Every part runs the whole time and is only gain-gated, so they share one
  // position. Showing it makes that visible rather than something to take on
  // trust: switch a part on at 0:30 and it arrives at 0:30.
  useEffect(() => {
    if (!player) return;
    let frame = 0;
    const tick = () => {
      setElapsed(player.elapsed());
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [player]);

  async function load() {
    const created = await createStemPlayer(
      trackId, available, () => setPlaying(false));
    playerRef.current = created;
    setPlayer(created);
    setEnabled(new Set(created.names));
    onActiveChange(true);
  }

  if (state === "none") {
    return (
      <div className="stems">
        <button
          className="sep"
          onClick={() => {
            requestStems(trackId);
            setState("pending");
          }}
        >
          Separate the parts
        </button>
        <p className="hint">
          Splits the song into guitar, bass, drums, vocals, piano and the rest so
          you can pick which ones you hear. Takes a couple of minutes.
        </p>
      </div>
    );
  }

  if (separating) {
    const percent = Math.round(progress * 100);
    return (
      <div className="stems">
        <div className="sep-progress">
          <div className="bar">
            <span style={{ width: `${Math.max(2, percent)}%` }} />
          </div>
          <p className="hint">
            {/* A bar at 0% for the first half minute reads as stalled, so the
                spinner carries the "still working" signal on its own. */}
            <span className="spinner" aria-hidden="true" />
            {state === "pending"
              ? "Queued — starting shortly."
              : `Separating the parts — ${percent}%`}
          </p>
          <p className="hint quiet">
            Listening to the whole song and pulling each instrument out of it.
            A couple of minutes; you can keep using the rest of the page.
          </p>
        </div>
      </div>
    );
  }

  if (state === "failed" || state === "unavailable") {
    return (
      <div className="stems">
        <p className="hint">Couldn't separate this song{error ? `: ${error}` : "."}</p>
      </div>
    );
  }

  if (!player) {
    return (
      <div className="stems">
        <button className="sep" onClick={load}>Open the mixer</button>
      </div>
    );
  }

  // The player's list, not the server's: a double-tracked guitar arrives as
  // one stem and becomes two faders, so only the player knows what there is
  // to hear. Already in display order.
  const ordered = player.names;
  const doubled = ordered.filter((n) => n.startsWith("guitar (")).length > 1;

  return (
    <div className="stems">
      <div className="mixhead">
        <button
          className="playbtn"
          onClick={() => {
            if (player.playing()) player.pause();
            else player.play();
            setPlaying(player.playing());
          }}
        >
          {playing ? "Pause" : "Play"} parts
        </button>

        <span className="clock">
          {timecode(elapsed)} / {timecode(player.duration)}
        </span>

        <input
          className="scrub"
          type="range"
          min={0}
          max={Math.max(1, Math.floor(player.duration))}
          value={Math.floor(elapsed)}
          aria-label="Position in the song"
          onChange={(event) => {
            player.seek(Number(event.target.value));
            setElapsed(player.elapsed());
          }}
        />
      </div>

      <p className="hint">
        Pick the parts you want to hear. They all run together, so switching one
        on drops it in where the song already is.
      </p>

      {doubled && (
        <p className="hint quiet">
          This song's rhythm guitar was recorded twice and panned apart, so the
          two takes are separate parts. Solo one to hear a single guitarist
          playing it — usually easier to follow than both at once.
        </p>
      )}

      <ul className="mixer">
        {ordered.map((name) => {
          const on = enabled.has(name);
          return (
            <li key={name} className={on ? "on" : undefined}>
              <button
                className="part"
                aria-pressed={on}
                onClick={() => setEnabled((current) => {
                  const next = new Set(current);
                  if (next.has(name)) next.delete(name);
                  else next.add(name);
                  return next;
                })}
              >
                <span className="dot" aria-hidden="true" />
                <span className="name">{name}</span>
              </button>
              <button
                className="only"
                title={`Hear ${name} on its own`}
                onClick={() => setEnabled(new Set([name]))}
              >
                only
              </button>
            </li>
          );
        })}
      </ul>

      <div className="mixfoot">
        <button className="only" onClick={() => setEnabled(new Set(ordered))}>
          All parts
        </button>
      </div>
    </div>
  );
}
