import { describe, expect, it, vi } from "vitest";
import { createControls, type PlayerElLike } from "./player";

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
