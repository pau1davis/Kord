import type { TrackResponse, TrackSummary } from "./api";

/**
 * Which song the workbench should be showing, or null for the dashboard.
 *
 * `picked` alone is not enough — it is null before the search result arrives —
 * and `data` alone is not enough either, because it outlives the song it
 * describes: clicking the wordmark clears `picked` immediately, but the fetched
 * response is only dropped by an effect that runs after the next render. For
 * that one render both the dashboard and the whole song view were mounted, so
 * the stem mixer never unmounted and kept sounding over the dashboard.
 *
 * Gating on `picked` makes the two views mutually exclusive by construction
 * rather than by the timing of a state update.
 */
export function songInView(
  picked: TrackSummary | null,
  data: TrackResponse | null,
): TrackSummary | null {
  if (!picked) return null;
  return data?.track ?? picked;
}
