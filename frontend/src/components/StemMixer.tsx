import { useEffect, useRef, useState } from "react";
import { getStems, requestStems, type StemState } from "../api";
import { createStemPlayer, type StemPlayer } from "../stemPlayer";
import { STEM_ORDER } from "../stems";

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
  const [muted, setMuted] = useState<Set<string>>(new Set());
  const [soloed, setSoloed] = useState<Set<string>>(new Set());
  const [playing, setPlaying] = useState(false);
  const playerRef = useRef<StemPlayer | null>(null);

  // Poll while separation is running. Roughly 2 minutes for a 4 minute song.
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
        if (s.status === "pending" || s.status === "running") {
          timer = window.setTimeout(poll, 2000);
        }
      } catch {
        if (live) timer = window.setTimeout(poll, 8000);
      }
    }
    poll();
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [trackId]);

  // One player per song. Tearing it down closes its AudioContext, which is
  // what actually frees the decoded buffers.
  useEffect(() => {
    return () => {
      playerRef.current?.destroy();
      playerRef.current = null;
      setPlayer(null);
      setPlaying(false);
      onActiveChange(false);
    };
  }, [trackId, onActiveChange]);

  useEffect(() => {
    player?.applyGains(muted, soloed);
  }, [player, muted, soloed]);

  const toggle = (set: Set<string>, name: string) => {
    const next = new Set(set);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    return next;
  };

  async function load() {
    const created = await createStemPlayer(trackId, available);
    playerRef.current = created;
    setPlayer(created);
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
          you can solo or mute each one. Takes a couple of minutes.
        </p>
      </div>
    );
  }

  if (state === "pending" || state === "running") {
    const percent = Math.round(progress * 100);
    return (
      <div className="stems">
        <div className="sep-progress">
          <div className="bar">
            <span style={{ width: `${Math.max(2, percent)}%` }} />
          </div>
          <p className="hint">
            {state === "pending"
              ? "Queued — starting shortly."
              : `Separating the parts — ${percent}%`}
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

  const ordered = STEM_ORDER.filter((name) => available.includes(name));

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
        <span className="hint">A practice aid — separation is never perfect.</span>
      </div>

      <ul className="mixer">
        {ordered.map((name) => {
          const isSolo = soloed.has(name);
          const isMuted = muted.has(name);
          return (
            <li key={name} className={isSolo ? "on" : undefined}>
              <span className="name">{name}</span>
              <button
                className={isMuted ? "tog on" : "tog"}
                onClick={() => setMuted((m) => toggle(m, name))}
              >
                mute
              </button>
              <button
                className={isSolo ? "tog on" : "tog"}
                onClick={() => setSoloed((s) => toggle(s, name))}
              >
                solo
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
