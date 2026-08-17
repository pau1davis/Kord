import { describe, expect, it } from "vitest";
import type { TrackResponse, TrackSummary } from "./api";
import { songInView } from "./navigation";

function summaryOf(id: string, title: string): TrackSummary {
  return { id, title, artist: "Band", album: null, duration_ms: 0, image: null };
}

const summary = summaryOf("a", "Song");
const other = summaryOf("b", "Other");
const response: TrackResponse = { track: other, status: "done" };

describe("songInView", () => {
  it("is the analysed track once the response arrives", () => {
    expect(songInView(summary, response)).toBe(other);
  });

  it("falls back to the search result while the analysis is still loading", () => {
    expect(songInView(summary, null)).toBe(summary);
  });

  it("shows nothing on the dashboard even while the last response lingers", () => {
    // The bug: clicking the wordmark clears `picked` synchronously but `data`
    // only on the next effect, so the song view stayed mounted over the
    // dashboard for a render — with its stem mixer still playing.
    expect(songInView(null, response)).toBeNull();
  });

  it("shows nothing when there is neither a pick nor a response", () => {
    expect(songInView(null, null)).toBeNull();
  });
});
