/** Display order: the parts this app is for come first. */
export const STEM_ORDER = [
  "guitar", "bass", "drums", "vocals", "piano", "other",
] as const;

/**
 * Gain per stem given the mute and solo sets.
 *
 * Solo is exclusive: as soon as anything is soloed, only soloed stems sound.
 * Soloing a stem that is also muted plays it — asking to hear something is an
 * unambiguous instruction, and the alternative is a button that does nothing.
 */
export function gainsFor(
  names: readonly string[],
  muted: ReadonlySet<string>,
  soloed: ReadonlySet<string>,
): Record<string, number> {
  const gains: Record<string, number> = {};
  for (const name of names) {
    if (soloed.size > 0) gains[name] = soloed.has(name) ? 1 : 0;
    else gains[name] = muted.has(name) ? 0 : 1;
  }
  return gains;
}

/**
 * Playhead position in seconds.
 *
 * Web Audio has no pause, so playback is stop-and-restart: `offset` is where
 * the current run began in the song and `startedAt` is the context clock
 * reading when it began. Null means stopped.
 */
export function elapsedAt(
  contextNow: number,
  startedAt: number | null,
  offset: number,
  duration: number,
): number {
  const raw = startedAt === null ? offset : offset + (contextNow - startedAt);
  return Math.min(duration, Math.max(0, raw));
}
