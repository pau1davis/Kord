import type { ChartEntry } from "./api";

export type LoopRange = { start: number; end: number };

/**
 * Audio time to chart time.
 *
 * Analysis trims leading silence, so chord timestamps start at the first sound
 * while the file still contains that silence. `sync_offset_ms` records exactly
 * how much — it is measured, not guessed, which is why nothing here needs
 * calibrating.
 */
export function chartTime(currentTime: number, syncOffsetMs: number): number {
  return currentTime - syncOffsetMs / 1000;
}

/**
 * Binary search for the index of the segment containing `t`, or -1.
 *
 * Split out from `findChordAt` so a caller that also needs the index (e.g. to
 * look up the next segment) doesn't have to re-scan with `indexOf` afterward.
 */
export function findChordIndexAt(entries: ChartEntry[], t: number): number {
  let lo = 0;
  let hi = entries.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const e = entries[mid];
    if (t < e.start_s) hi = mid - 1;
    else if (t >= e.end_s) lo = mid + 1;
    else return mid;
  }
  return -1;
}

/** Binary search for the segment containing `t`. Start inclusive, end exclusive. */
export function findChordAt(entries: ChartEntry[], t: number): ChartEntry | null {
  const index = findChordIndexAt(entries, t);
  return index === -1 ? null : entries[index];
}

/**
 * Collapse runs of very short chords for display only.
 *
 * Mouth for War changes chord 171 times in 4 minutes, sometimes twice a second;
 * a large display strobes unreadably. The dominant chord of a collapsed run
 * wins. The input is never modified — the chord sheet still shows every change.
 */
export function collapseShortSegments(
  entries: ChartEntry[],
  minSeconds: number,
): ChartEntry[] {
  if (entries.length === 0) return [];

  const out: ChartEntry[] = [];
  let run: ChartEntry[] = [];

  const flush = () => {
    if (run.length === 0) return;
    const span = run[run.length - 1].end_s - run[0].start_s;
    const dominant = run.reduce((best, e) =>
      e.end_s - e.start_s > best.end_s - best.start_s ? e : best);
    out.push({ ...dominant, start_s: run[0].start_s, end_s: run[0].start_s + span });
    run = [];
  };

  for (const e of entries) {
    if (e.end_s - e.start_s >= minSeconds) {
      flush();
      out.push({ ...e });
    } else {
      run.push(e);
      const span = run[run.length - 1].end_s - run[0].start_s;
      if (span >= minSeconds) flush();
    }
  }
  flush();
  return out;
}

/** Seek target when playback leaves the loop, or null if it is still inside. */
export function loopTarget(
  t: number,
  loop: LoopRange | null,
  syncOffsetS: number,
): number | null {
  if (loop === null) return null;
  if (t >= loop.end || t < loop.start) return loop.start + syncOffsetS;
  return null;
}
