import { describe, expect, it } from "vitest";
import { elapsedAt, gainsFor, isSeparating, STEM_ORDER } from "./stems";

describe("isSeparating", () => {
  it("covers the whole of the wait, not just the running part", () => {
    // Pressing the button sets "pending" before the server has been asked, so
    // a poller that only re-armed on "running" would never see the job start.
    expect(isSeparating("pending")).toBe(true);
    expect(isSeparating("running")).toBe(true);
  });

  it("is over once there is something to listen to, or nothing coming", () => {
    expect(isSeparating("done")).toBe(false);
    expect(isSeparating("none")).toBe(false);
    expect(isSeparating("failed")).toBe(false);
    expect(isSeparating("unavailable")).toBe(false);
  });
});

describe("gainsFor", () => {
  const all = ["drums", "bass", "guitar"];

  it("plays every part that is switched on", () => {
    expect(gainsFor(all, new Set(all))).toEqual(
      { drums: 1, bass: 1, guitar: 1 });
  });

  it("silences the parts that are switched off", () => {
    expect(gainsFor(all, new Set(["guitar"]))).toEqual(
      { drums: 0, bass: 0, guitar: 1 });
  });

  it("plays any combination you pick, not just one", () => {
    // The whole point: learning a bassline against the drums means hearing
    // exactly those two and nothing else.
    expect(gainsFor(all, new Set(["bass", "drums"]))).toEqual(
      { drums: 1, bass: 1, guitar: 0 });
  });

  it("everything off is silence, not a reset to everything on", () => {
    expect(gainsFor(all, new Set())).toEqual(
      { drums: 0, bass: 0, guitar: 0 });
  });

  it("ignores a name that is not one of the stems", () => {
    expect(gainsFor(all, new Set(["trombone"]))).toEqual(
      { drums: 0, bass: 0, guitar: 0 });
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
