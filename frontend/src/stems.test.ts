import { describe, expect, it } from "vitest";
import { elapsedAt, gainsFor, STEM_ORDER } from "./stems";

describe("gainsFor", () => {
  const all = ["drums", "bass", "guitar"];

  it("plays everything when nothing is touched", () => {
    expect(gainsFor(all, new Set(), new Set())).toEqual(
      { drums: 1, bass: 1, guitar: 1 });
  });

  it("silences a muted stem", () => {
    expect(gainsFor(all, new Set(["drums"]), new Set())).toEqual(
      { drums: 0, bass: 1, guitar: 1 });
  });

  it("solo silences everything else", () => {
    expect(gainsFor(all, new Set(), new Set(["guitar"]))).toEqual(
      { drums: 0, bass: 0, guitar: 1 });
  });

  it("solo beats mute on the same stem", () => {
    // Soloing a stem you had muted is an unambiguous request to hear it.
    expect(gainsFor(all, new Set(["guitar"]), new Set(["guitar"]))).toEqual(
      { drums: 0, bass: 0, guitar: 1 });
  });

  it("supports soloing several stems at once", () => {
    expect(gainsFor(all, new Set(), new Set(["bass", "guitar"]))).toEqual(
      { drums: 0, bass: 1, guitar: 1 });
  });

  it("mutes still apply among non-soloed stems", () => {
    expect(gainsFor(all, new Set(["bass"]), new Set())).toEqual(
      { drums: 1, bass: 0, guitar: 1 });
  });
});

describe("elapsedAt", () => {
  it("is the offset before playback starts", () => {
    expect(elapsedAt(5, null, 12, 200)).toBe(12);
  });

  it("advances with the context clock once started", () => {
    expect(elapsedAt(10, 4, 12, 200)).toBeCloseTo(18);
  });

  it("never runs past the end of the song", () => {
    expect(elapsedAt(999, 0, 0, 200)).toBe(200);
  });

  it("never goes negative", () => {
    expect(elapsedAt(0, 5, 0, 200)).toBe(0);
  });
});

describe("STEM_ORDER", () => {
  it("leads with the parts you play", () => {
    // A guitarist and bassist opens this to find guitar and bass, not piano.
    expect(STEM_ORDER[0]).toBe("guitar");
    expect(STEM_ORDER[1]).toBe("bass");
    expect(STEM_ORDER).toHaveLength(6);
  });
});
