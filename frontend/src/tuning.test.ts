import { describe, expect, it } from "vitest";
import type { Tuning } from "./api";
import { referenceCaveat, referenceLine } from "./tuning";

const tuning = (cents: number, reliable = true): Tuning =>
  ({ reference_cents: cents, agreement: 0.98, reliable });

describe("referenceLine", () => {
  it("tells you which way to move your own tuning, not what the record did", () => {
    // "23 cents sharp" is a fact about the record; a player needs an action.
    expect(referenceLine(tuning(23))).toBe("Tune up 23¢ to play along");
    expect(referenceLine(tuning(-36))).toBe("Tune down 36¢ to play along");
  });

  it("calls a few cents concert pitch rather than an instruction", () => {
    // Under a fifth of a fret, and less than a guitar drifts across a song.
    expect(referenceLine(tuning(6.5))).toBe("Concert pitch (A440)");
    expect(referenceLine(tuning(-3))).toBe("Concert pitch (A440)");
  });

  it("says nothing at all when the reading cannot be trusted", () => {
    expect(referenceLine(tuning(33, false))).toBeNull();
    expect(referenceLine(null)).toBeNull();
    expect(referenceLine(undefined)).toBeNull();
  });
});

describe("referenceCaveat", () => {
  it("blames the source when it was speed-adjusted", () => {
    const text = referenceCaveat(tuning(33, false), ["speed_adjusted"]);
    expect(text).toContain("different speed");
  });

  it("blames the song when the windows disagreed", () => {
    const text = referenceCaveat(tuning(12, false), []);
    expect(text).toContain("disagreed");
  });

  it("stays quiet when there is a good reading to show instead", () => {
    expect(referenceCaveat(tuning(23), [])).toBeNull();
  });

  it("stays quiet for a song analysed before tuning was measured", () => {
    expect(referenceCaveat(null, [])).toBeNull();
  });
});
