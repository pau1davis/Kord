import { useEffect, useState } from "react";
import { snapshotOf, type Player } from "../player";

/**
 * The current audio position, sampled once per frame.
 *
 * `currentTime` is an exact clock available on demand, so there is no
 * interpolation, no event anchoring and no drift to correct.
 */
export function usePlayhead(player: Player | null) {
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    // This hook's state still describes the previous song until something says
    // otherwise, and swapping the player fires no events — so seed from the new
    // element first, or the transport shows "Pause" over a stopped song.
    const initial = snapshotOf(player?.el ?? null);
    setCurrentTime(initial.currentTime);
    setPlaying(initial.playing);
    setDuration(initial.duration);

    if (!player) return;
    const { el } = player;
    let frame = 0;

    const tick = () => {
      setCurrentTime(el.currentTime);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onMeta = () => setDuration(el.duration || 0);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("loadedmetadata", onMeta);

    return () => {
      cancelAnimationFrame(frame);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("loadedmetadata", onMeta);
    };
  }, [player]);

  return { currentTime, playing, duration };
}
