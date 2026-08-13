/**
 * A plain <audio> element playing the file Kord analysed.
 *
 * Using the analysed audio is what makes sync exact: chord timestamps came from
 * this file, so chart time and audio time are the same clock. There is nothing
 * to calibrate and nothing to drift.
 */
export type Player = {
  el: HTMLAudioElement;
  play(): Promise<void>;
  pause(): void;
  toggle(): void;
  seek(seconds: number): void;
  setRate(rate: number): void;
  destroy(): void;
};

export function createPlayer(trackId: string): Player {
  const el = new Audio(`/api/track/${trackId}/audio`);
  el.preload = "metadata";
  // Default is already true; set explicitly because the whole slow-down feature
  // depends on it and a silent regression here would be hard to spot.
  el.preservesPitch = true;

  return {
    el,
    play: () => el.play(),
    pause: () => el.pause(),
    toggle: () => void (el.paused ? el.play() : el.pause()),
    seek: (seconds) => {
      el.currentTime = Math.max(0, seconds);
    },
    setRate: (rate) => {
      el.playbackRate = rate;
    },
    destroy: () => {
      el.pause();
      el.src = "";
    },
  };
}
