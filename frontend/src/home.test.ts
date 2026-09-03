import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { homeMode } from "./home";

describe("homeMode", () => {
  it("shows the taste ring when Spotify answered", () => {
    expect(homeMode(true, null)).toBe("taste");
  });

  it("falls back to local music rather than a wall when not signed in", () => {
    // The whole point: no account must not mean no app.
    expect(homeMode(false, new ApiError(401, "no session"))).toBe("local");
  });

  it("still shows something when Spotify simply returned nothing", () => {
    expect(homeMode(false, null)).toBe("local");
  });

  it("reports a real failure as an error, not as being signed out", () => {
    expect(homeMode(false, new ApiError(500, "boom"))).toBe("error");
    expect(homeMode(false, new ApiError(0, "server down"))).toBe("error");
  });
});
