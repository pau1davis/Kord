import { describe, expect, it, vi } from "vitest";
import { createControls, snapshotOf, type PlayerElLike } from "./player";

// A minimal fake shaped like the slice of HTMLAudioElement the controls
// touch. No jsdom, no real <audio> element, no network.
function fakeEl(overrides: Partial<PlayerElLike> = {}): PlayerElLike {
  return {
    play: vi.fn(() => Promise.resolve()),
    pause: vi.fn(),
    paused: true,
    currentTime: 0,
    playbackRate: 1,
    load: vi.fn(),
    removeAttribute: vi.fn(),
    ...overrides,
  };
}

describe("seek", () => {
  it("clamps a negative seek to 0", () => {
    const el = fakeEl({ currentTime: 5 });
    const { seek } = createControls(el);
    seek(-10);
    expect(el.currentTime).toBe(0);
  });

  it("passes a positive seek through unchanged", () => {
    const el = fakeEl();
    const { seek } = createControls(el);
    seek(42);
    expect(el.currentTime).toBe(42);
  });
});

describe("toggle", () => {
  it("plays when paused", () => {
    const el = fakeEl({ paused: true });
    const { toggle } = createControls(el);
    toggle();
    expect(el.play).toHaveBeenCalledOnce();
    expect(el.pause).not.toHaveBeenCalled();
  });

  it("pauses when playing", () => {
    const el = fakeEl({ paused: false });
    const { toggle } = createControls(el);
    toggle();
    expect(el.pause).toHaveBeenCalledOnce();
    expect(el.play).not.toHaveBeenCalled();
  });
});

describe("snapshotOf", () => {
  it("reports a fresh element as paused at the start", () => {
    expect(snapshotOf({ currentTime: 0, paused: true, duration: 210 }))
      .toEqual({ currentTime: 0, playing: false, duration: 210 });
  });

  it("reports an element that is already running as playing", () => {
    expect(snapshotOf({ currentTime: 12.5, paused: false, duration: 210 }))
      .toEqual({ currentTime: 12.5, playing: true, duration: 210 });
  });

  it("treats a missing player as stopped rather than leaving stale state", () => {
    // Switching to a song with no audio must not leave the previous song's
    // transport reading "Pause".
    expect(snapshotOf(null))
      .toEqual({ currentTime: 0, playing: false, duration: 0 });
  });

  it("reports an unknown duration as zero, not NaN", () => {
    // A media element reports NaN before metadata loads, which would render.
    expect(snapshotOf({ currentTime: 0, paused: true, duration: NaN }).duration)
      .toBe(0);
  });
});
