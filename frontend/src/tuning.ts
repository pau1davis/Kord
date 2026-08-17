import type { Tuning } from "./api";

/**
 * Below this, the record is at concert pitch as far as a player is concerned.
 * Ten cents is under a fifth of the gap between two adjacent frets, and inside
 * what a guitar drifts across a song anyway.
 */
export const AUDIBLE_CENTS = 10;

/** How the reference pitch should read, or null when there is nothing to say. */
export function referenceLine(tuning: Tuning | null | undefined): string | null {
  if (!tuning || !tuning.reliable) return null;
  const cents = Math.round(tuning.reference_cents);
  if (Math.abs(cents) < AUDIBLE_CENTS) return "Concert pitch (A440)";
  // Said from the player's side of the problem: what they have to do to their
  // own guitar, not what the record did. "23¢ sharp" is a fact about the
  // record; "tune up 23¢" is the same fact as an instruction.
  return `Tune ${cents > 0 ? "up" : "down"} ${Math.abs(cents)}¢ to play along`;
}

/** Why no reference pitch is being shown, when there is a reason worth giving. */
export function referenceCaveat(
  tuning: Tuning | null | undefined, flags: readonly string[],
): string | null {
  if (!tuning || tuning.reliable) return null;
  if (flags.includes("speed_adjusted")) {
    return "Can't tell how this record is tuned — the source runs at a slightly "
      + "different speed, which shifts its pitch by about as much as tuning does.";
  }
  return "Can't tell how this record is tuned — different parts of the song "
    + "disagreed about where A sits.";
}
