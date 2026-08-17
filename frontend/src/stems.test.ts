import { describe, expect, it } from "vitest";
import {
  baseStem, correlation, elapsedAt, gainsFor, isSeparating, orderParts,
  partNames, STEM_ORDER,
} from "./stems";

describe("correlation", () => {
  const ramp = (n: number, f: (i: number) => number) =>
    Float32Array.from({ length: n }, (_, i) => f(i));

  it("is 1 for the same signal in both channels", () => {
    const a = ramp(4096, (i) => Math.sin(i / 7));
    expect(correlation(a, a)).toBeCloseTo(1, 5);
  });

  it("is -1 for a polarity-flipped channel", () => {
    const a = ramp(4096, (i) => Math.sin(i / 7));
    const b = ramp(4096, (i) => -Math.sin(i / 7));
    expect(correlation(a, b)).toBeCloseTo(-1, 5);
  });

  it("is near zero for two unrelated performances", () => {
    const a = ramp(8192, (i) => Math.sin(i / 7));
    const b = ramp(8192, (i) => Math.sin(i / 13 + 1.1));
    expect(Math.abs(correlation(a, b))).toBeLessThan(0.3);
  });

  it("calls a silent channel identical rather than uncorrelated", () => {
    // Silence has no shape to compare, and a zero here would advertise a
    // second guitar that is not there.
    const a = ramp(4096, (i) => Math.sin(i / 7));
    expect(correlation(a, new Float32Array(4096))).toBe(1);
  });
});

describe("partNames", () => {
  it("splits a double-tracked guitar into its two takes", () => {
    expect(partNames("guitar", 2, 0.0)).toEqual(
      ["guitar (left)", "guitar (right)"]);
  });

  it("leaves a single guitar alone", () => {
    // Superdrag's Cynicality reads 1.00 — one take, panned centre.
    expect(partNames("guitar", 2, 1.0)).toEqual(["guitar"]);
  });

  it("treats a polarity-flipped copy as one take, not two", () => {
    // Strong negative correlation means the same performance with its phase
    // inverted — a mixing accident, not a second guitarist.
    expect(partNames("guitar", 2, -0.9)).toEqual(["guitar"]);
    expect(partNames("guitar", 2, -0.1)).toHaveLength(2);
  });

  it("never splits a mono stem", () => {
    expect(partNames("guitar", 1, 0.0)).toEqual(["guitar"]);
  });

  it("never splits drums, however wide they are", () => {
    // Overheads are decorrelated too, but they are one kit from two places,
    // not two performances.
    expect(partNames("drums", 2, 0.0)).toEqual(["drums"]);
    expect(partNames("vocals", 2, 0.0)).toEqual(["vocals"]);
  });
});

describe("orderParts", () => {
  it("keeps STEM_ORDER and puts a split guitar's halves first and adjacent", () => {
    expect(orderParts(["drums", "guitar (right)", "bass", "guitar (left)"]))
      .toEqual(["guitar (left)", "guitar (right)", "bass", "drums"]);
  });

  it("puts anything unrecognised at the end rather than dropping it", () => {
    expect(orderParts(["mystery", "bass"])).toEqual(["bass", "mystery"]);
  });
});

describe("baseStem", () => {
  it("reads through to the instrument", () => {
    expect(baseStem("guitar (left)")).toBe("guitar");
    expect(baseStem("bass")).toBe("bass");
  });
});

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
