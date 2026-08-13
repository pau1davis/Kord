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

// The subset of HTMLAudioElement that the control logic below actually
// reads or writes. Extracted so that logic can be exercised in tests with a
// plain fake object — no jsdom, no real <audio> element, no network.
export type PlayerElLike = Pick<
  HTMLAudioElement,
  "play" | "pause" | "paused" | "currentTime" | "playbackRate" | "load" | "removeAttribute"
>;

// Builds the control methods for a given element-like object. Split out from
// createPlayer purely for testability of the pure branching/clamping logic
// (seek's clamp, toggle's play/pause branch); createPlayer is the only
// caller in production and always passes a real <audio> element.
export function createControls(el: PlayerElLike): Omit<Player, "el"> {
  return {
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
      // Clearing src alone doesn't reliably abort an in-flight streamed
      // download in every browser — the pending GET can keep running until
      // the element is GC'd. removeAttribute + load() forces the abort.
      // (Assigning "" instead of removing the attribute can also resolve
      // against the document base URL and trigger a spurious request.)
      el.removeAttribute("src");
      el.load();
    },
  };
}

export function createPlayer(trackId: string): Player {
  const el = new Audio(`/api/track/${trackId}/audio`);
  el.preload = "metadata";
  // Default is already true; set explicitly because the whole slow-down feature
  // depends on it and a silent regression here would be hard to spot.
  el.preservesPitch = true;

  return { el, ...createControls(el) };
}
