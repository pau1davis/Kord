import { ApiError } from "./api";

/**
 * What the home screen should show.
 *
 * Being signed out is not an error — it is the normal state for someone who
 * has no reason to care about Spotify. Only a genuine failure is an error.
 */
export function homeMode(
  hasTop: boolean, failed: ApiError | null,
): "taste" | "local" | "error" {
  if (hasTop) return "taste";
  if (failed && failed.status !== 401) return "error";
  return "local";
}
