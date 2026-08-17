export type TabNote = {
  start_s: number;
  end_s: number;
  midi: number;
  confidence: number;
  string: number | null;
  fret: number | null;
};

export type TabResponse = {
  part: string;
  tuning: string;
  strings: number;
  bars: number[];
  notes: TabNote[];
  unplayable: number;
};

/**
 * Below this the transcriber was guessing, and the note renders dimmed.
 *
 * Calibrated against the measurement in
 * docs/notes/2026-08-17-transcription-accuracy.md: on a real song
 * this dims about three quarters of the guitar notes and none of the bass,
 * which is the honest difference between the two engines.
 */
export const DIM_BELOW = 0.5;

/** String names low to high, for the stave's left edge. */
export function stringLabels(count: number): string[] {
  return count === 4 ? ["E", "A", "D", "G"] : ["E", "A", "D", "G", "B", "e"];
}

export type Bar = {
  index: number;
  start_s: number;
  end_s: number;
  notes: TabNote[];
};

/**
 * Notes grouped into the bar they start in.
 *
 * Done here rather than server-side because the bar a note belongs to is a
 * layout question, and the same notes are re-laid-out whenever the tuning
 * changes without another request.
 */
export function toBars(notes: readonly TabNote[], starts: readonly number[]): Bar[] {
  const bounds = starts.length ? starts : [0];
  const bars: Bar[] = bounds.map((start, index) => ({
    index,
    start_s: start,
    end_s: bounds[index + 1] ?? Number.POSITIVE_INFINITY,
    notes: [],
  }));
  for (const note of notes) {
    // A note before the first bar line — a pickup, or one nudged early by the
    // sync offset — belongs to the first bar rather than nowhere.
    let index = 0;
    for (let i = 0; i < bounds.length; i++) {
      if (note.start_s >= bounds[i]) index = i;
    }
    bars[index].notes.push(note);
  }
  return bars;
}

/** Which bar contains this moment, or -1 before the first one starts. */
export function barIndexAt(bars: readonly Bar[], now: number): number {
  for (let i = bars.length - 1; i >= 0; i--) {
    if (now >= bars[i].start_s) return i;
  }
  return bars.length ? 0 : -1;
}

/**
 * Where in the song a bar begins, for seeking when you scroll to it.
 *
 * Scrolling the tab is navigation, so the view has to be able to answer "what
 * time is the thing I am looking at?" — this is that answer.
 */
export function timeOfBar(bars: readonly Bar[], index: number): number {
  if (!bars.length) return 0;
  const clamped = Math.min(bars.length - 1, Math.max(0, index));
  return bars[clamped].start_s;
}
