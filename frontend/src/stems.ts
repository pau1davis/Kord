/** Display order: the parts this app is for come first. */
export const STEM_ORDER = [
  "guitar", "bass", "drums", "vocals", "piano", "other",
] as const;

/**
 * Gain per stem: one for the parts you have switched on, zero for the rest.
 *
 * Deliberately not a mixing desk. Mute-and-solo is a convention that assumes
 * you already know it, and the thing a player actually wants is to choose the
 * handful of parts they are working against — bass and drums while learning a
 * line, say. So each part is simply on or off, and any combination is valid.
 */
export function gainsFor(
  names: readonly string[],
  enabled: ReadonlySet<string>,
): Record<string, number> {
  const gains: Record<string, number> = {};
  for (const name of names) gains[name] = enabled.has(name) ? 1 : 0;
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
