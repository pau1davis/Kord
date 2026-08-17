/** Display order: the parts this app is for come first. */
export const STEM_ORDER = [
  "guitar", "bass", "drums", "vocals", "piano", "other",
] as const;

/**
 * Above this, the two channels are the same performance and there is nothing
 * to pull apart. Measured across the library: a doubled rhythm guitar reads
 * 0.00 to 0.50, a single guitar reads 1.00. Nothing lands near the line.
 */
export const DOUBLE_TRACKED_MAX_CORR = 0.7;

/**
 * Pearson correlation between two channels.
 *
 * Sampled every `stride`th frame rather than every frame: this runs on ten
 * million samples at decode time, and a correlation estimate does not get
 * meaningfully better past a few hundred thousand points.
 */
export function correlation(
  left: Float32Array, right: Float32Array, stride = 16,
): number {
  const n = Math.min(left.length, right.length);
  let sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0, count = 0;
  for (let i = 0; i < n; i += stride) {
    const x = left[i], y = right[i];
    sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y;
    count++;
  }
  if (count === 0) return 1;
  const cov = sxy / count - (sx / count) * (sy / count);
  const vx = sxx / count - (sx / count) ** 2;
  const vy = syy / count - (sy / count) ** 2;
  // A silent channel has no variance, so there is no shape to compare. Call it
  // identical: silence is not a second guitar.
  if (vx <= 1e-12 || vy <= 1e-12) return 1;
  return cov / Math.sqrt(vx * vy);
}

/**
 * What to call this stem's parts — one name, or two when it is double tracked.
 *
 * Rock production records a rhythm part twice and hard-pans the takes, so the
 * two guitars are already in separate channels and averaging them to mono is
 * what was hiding the second one.
 *
 * Only guitar. Drum overheads and room mics are just as decorrelated, but
 * their channels are one kit heard from two places, not two performances —
 * splitting those would offer a fader that means nothing.
 */
export function partNames(
  stem: string, channels: number, corr: number,
): string[] {
  if (stem !== "guitar" || channels < 2) return [stem];
  if (Math.abs(corr) > DOUBLE_TRACKED_MAX_CORR) return [stem];
  return [`${stem} (left)`, `${stem} (right)`];
}

/** The stem a part came from: "guitar (left)" is a guitar. */
export function baseStem(part: string): string {
  return part.split(" (")[0];
}

/** Parts in STEM_ORDER, with a split stem's halves kept adjacent and in order. */
export function orderParts(names: readonly string[]): string[] {
  const rank = (part: string) => {
    const i = (STEM_ORDER as readonly string[]).indexOf(baseStem(part));
    return i === -1 ? STEM_ORDER.length : i;
  };
  return [...names].sort(
    (a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

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
 * Is separation underway — queued or actually running?
 *
 * One definition serving both the progress panel and the polling loop, because
 * the bug was the two disagreeing: pressing "Separate the parts" set the status
 * to pending optimistically, which the panel rendered as "Queued", but the
 * poller had already stopped when the initial fetch came back "none" and had no
 * reason to start again. The message sat there unchanged until a reload.
 */
export function isSeparating(status: string): boolean {
  return status === "pending" || status === "running";
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
