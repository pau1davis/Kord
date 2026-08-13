import { describe, expect, it } from "vitest";
import { chartTime, collapseShortSegments, findChordAt, loopTarget } from "./chart";
import type { ChartEntry } from "./api";

const entry = (start: number, end: number, label: string): ChartEntry => ({
  start_s: start, end_s: end, label, quality: "major",
  roman: "I", hue: 40, uncertain: false,
});

describe("chartTime", () => {
  it("subtracts the analysis trim offset", () => {
    expect(chartTime(10, 511)).toBeCloseTo(9.489);
  });

  it("is identity when nothing was trimmed", () => {
    expect(chartTime(10, 0)).toBe(10);
  });

  it("can go negative during the trimmed intro", () => {
    expect(chartTime(0.2, 511)).toBeLessThan(0);
  });
});

describe("findChordAt", () => {
  const entries = [entry(0, 1, "C"), entry(1, 2, "G"), entry(2, 3, "Am")];

  it("finds the containing segment", () => {
    expect(findChordAt(entries, 1.5)?.label).toBe("G");
  });

  it("treats the start as inclusive and the end as exclusive", () => {
    expect(findChordAt(entries, 1)?.label).toBe("G");
    expect(findChordAt(entries, 2)?.label).toBe("Am");
  });

  it("returns null before the first and after the last", () => {
    expect(findChordAt(entries, -0.5)).toBeNull();
    expect(findChordAt(entries, 99)).toBeNull();
  });

  it("returns null inside a gap", () => {
    expect(findChordAt([entry(0, 1, "C"), entry(5, 6, "G")], 3)).toBeNull();
  });

  it("handles an empty chart", () => {
    expect(findChordAt([], 1)).toBeNull();
  });
});

describe("collapseShortSegments", () => {
  it("merges runs shorter than the minimum", () => {
    // The C+G run only spans 0.2s, so it cannot stand on its own either — it
    // is absorbed into Am, the longer neighbour, rather than emitted at 0.2s.
    const out = collapseShortSegments(
      [entry(0, 0.1, "C"), entry(0.1, 0.2, "G"), entry(0.2, 2, "Am")], 0.4);
    expect(out).toHaveLength(1);
    expect(out[0].label).toBe("Am");
    expect(out[0].start_s).toBeCloseTo(0);
    expect(out[0].end_s).toBeCloseTo(2);
  });

  it("never emits a segment under the minimum", () => {
    // The invariant the hero display depends on. A lone short chord between
    // two long ones used to pass straight through and strobe.
    const out = collapseShortSegments(
      [entry(0, 2, "C"), entry(2, 2.09, "F#"), entry(2.09, 4, "G")], 0.4);
    expect(out.every((e) => e.end_s - e.start_s >= 0.4)).toBe(true);
    expect(out.map((e) => e.label)).toEqual(["C", "G"]);
  });

  it("absorbs a short segment into whichever neighbour is longer", () => {
    const out = collapseShortSegments(
      [entry(0, 0.6, "C"), entry(0.6, 0.7, "F#"), entry(0.7, 5, "G")], 0.4);
    expect(out.map((e) => e.label)).toEqual(["C", "G"]);
    expect(out[1].start_s).toBeCloseTo(0.6);
  });

  it("absorbs a trailing short segment backwards", () => {
    const out = collapseShortSegments(
      [entry(0, 3, "C"), entry(3, 3.05, "B")], 0.4);
    expect(out).toHaveLength(1);
    expect(out[0].label).toBe("C");
    expect(out[0].end_s).toBeCloseTo(3.05);
  });

  it("keeps a single segment even when the whole song is shorter", () => {
    const out = collapseShortSegments([entry(0, 0.1, "C")], 0.4);
    expect(out).toHaveLength(1);
    expect(out[0].label).toBe("C");
  });

  it("keeps long segments untouched", () => {
    const input = [entry(0, 2, "C"), entry(2, 4, "G")];
    expect(collapseShortSegments(input, 0.4)).toEqual(input);
  });

  it("does not mutate its input", () => {
    const input = [entry(0, 0.1, "C"), entry(0.1, 2, "G")];
    const copy = JSON.parse(JSON.stringify(input));
    collapseShortSegments(input, 0.4);
    expect(input).toEqual(copy);
  });

  it("keeps total coverage identical", () => {
    const input = [entry(0, 0.1, "C"), entry(0.1, 0.2, "G"), entry(0.2, 3, "Am")];
    const out = collapseShortSegments(input, 0.4);
    expect(out[0].start_s).toBe(0);
    expect(out[out.length - 1].end_s).toBe(3);
  });
});

describe("loopTarget", () => {
  it("returns the seek target once past the loop end", () => {
    expect(loopTarget(9.9, { start: 4, end: 9.5 }, 0.511)).toBeCloseTo(4.511);
  });

  it("returns null inside the loop", () => {
    expect(loopTarget(6, { start: 4, end: 9.5 }, 0.511)).toBeNull();
  });

  it("returns null with no loop set", () => {
    expect(loopTarget(6, null, 0.511)).toBeNull();
  });

  it("also wraps when playback starts before the loop", () => {
    expect(loopTarget(1, { start: 4, end: 9.5 }, 0)).toBeCloseTo(4);
  });
});
