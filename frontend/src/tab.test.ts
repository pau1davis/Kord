import { describe, expect, it } from "vitest";
import {
  barIndexAt, DIM_BELOW, stringLabels, timeOfBar, toBars, type TabNote,
} from "./tab";

const note = (start: number, overrides: Partial<TabNote> = {}): TabNote => ({
  start_s: start, end_s: start + 0.2, midi: 45, confidence: 0.9,
  string: 0, fret: 5, ...overrides,
});

describe("toBars", () => {
  it("puts each note in the bar it starts in", () => {
    const bars = toBars([note(0.1), note(2.1), note(2.6)], [0, 2, 4]);
    expect(bars.map((b) => b.notes.length)).toEqual([1, 2, 0]);
  });

  it("keeps a pickup note rather than dropping it", () => {
    // A note before the first bar line is real music, not an error.
    const bars = toBars([note(0.0)], [0.5, 2.5]);
    expect(bars[0].notes).toHaveLength(1);
  });

  it("gives every bar a start and an end", () => {
    const bars = toBars([], [0, 2, 4]);
    expect(bars[0].end_s).toBe(2);
    expect(bars[2].end_s).toBe(Number.POSITIVE_INFINITY);
  });

  it("renders as one bar when the song has no beat grid", () => {
    const bars = toBars([note(1), note(9)], []);
    expect(bars).toHaveLength(1);
    expect(bars[0].notes).toHaveLength(2);
  });

  it("loses no notes, wherever they fall", () => {
    const notes = [0, 1.9, 2.0, 3.99, 4.0, 99].map((t) => note(t));
    const total = toBars(notes, [0, 2, 4])
      .reduce((sum, bar) => sum + bar.notes.length, 0);
    expect(total).toBe(notes.length);
  });
});

describe("barIndexAt", () => {
  const bars = toBars([], [0, 2, 4]);

  it("finds the bar the playhead is in", () => {
    expect(barIndexAt(bars, 0)).toBe(0);
    expect(barIndexAt(bars, 2.5)).toBe(1);
    expect(barIndexAt(bars, 99)).toBe(2);
  });

  it("stays on the first bar before the music starts", () => {
    expect(barIndexAt(toBars([], [1.5, 3]), 0.2)).toBe(0);
  });

  it("has no bar to point at when there are none", () => {
    expect(barIndexAt([], 5)).toBe(-1);
  });
});

describe("timeOfBar", () => {
  const bars = toBars([], [0, 2, 4]);

  it("is where that bar begins, which is where playing it starts", () => {
    expect(timeOfBar(bars, 1)).toBe(2);
  });

  it("clamps rather than returning undefined off either end", () => {
    expect(timeOfBar(bars, -5)).toBe(0);
    expect(timeOfBar(bars, 99)).toBe(4);
    expect(timeOfBar([], 3)).toBe(0);
  });
});

describe("stringLabels", () => {
  it("gives a bass four strings and a guitar six", () => {
    expect(stringLabels(4)).toEqual(["E", "A", "D", "G"]);
    expect(stringLabels(6)).toEqual(["E", "A", "D", "G", "B", "e"]);
  });
});

describe("DIM_BELOW", () => {
  it("sits where the accuracy measurement put it", () => {
    // Dims roughly three quarters of guitar notes and none of the bass, which
    // is the real difference between the two engines rather than a guess.
    expect(DIM_BELOW).toBe(0.5);
  });
});
