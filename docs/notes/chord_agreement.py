"""How many transcribed notes belong to the chord sounding at that moment?

Not a correctness test — passing tones, suspensions and chromatic runs are real
music, so some out-of-chord notes are expected. A rate far above what theory
predicts means the engine is inventing notes, and that is what this catches.

Kord's own chord detection is the reference, which is defensible because it is
separately validated and was built against the same library.
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, "backend")

STEMS = os.path.expanduser("~/.kord/stems")
DB = os.path.expanduser("~/.kord/kord.db")

# Pitch classes above the root, by quality. Anything else is "foreign".
TONES = {
    "major": (0, 4, 7), "minor": (0, 3, 7), "power": (0, 7),
    "major7": (0, 4, 7, 11), "minor7": (0, 3, 7, 10), "dominant7": (0, 4, 7, 10),
    "diminished": (0, 3, 6), "augmented": (0, 4, 8), "dim7": (0, 3, 6, 9),
    "hdim7": (0, 3, 6, 10), "sus2": (0, 2, 7), "sus4": (0, 5, 7),
}


def chord_at(segments, t):
    for s in segments:
        if s["start_s"] <= t < s["end_s"]:
            return s
    return None


def main():
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict

    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    lines = [f"{'song':38} {'notes':>7} {'foreign':>8} {'octave':>7}"]
    for d in sorted(os.listdir(STEMS)):
        row = conn.execute(
            "SELECT payload FROM analysis WHERE spotify_id=? ORDER BY rowid DESC",
            (d,)).fetchone()
        track = conn.execute(
            "SELECT artist, title FROM track WHERE spotify_id=?", (d,)).fetchone()
        path = os.path.join(STEMS, d, "guitar.m4a")
        if row is None or track is None or not os.path.exists(path):
            continue
        segments = json.loads(row["payload"])["chord_segments"]
        _, _, notes = predict(path, ICASSP_2022_MODEL_PATH)

        total = foreign = 0
        by_onset: dict[float, list[int]] = {}
        for start, _end, midi, *_ in notes:
            seg = chord_at(segments, start)
            by_onset.setdefault(round(float(start), 2), []).append(int(midi))
            if seg is None or seg["root"] < 0 or seg["quality"] not in TONES:
                continue
            total += 1
            if (int(midi) - seg["root"]) % 12 not in TONES[seg["quality"]]:
                foreign += 1

        # Simultaneous notes an exact octave apart: the failure mode the
        # synthetic material showed, which chord agreement cannot see because
        # an octave of a chord tone is still a chord tone.
        octaves = sum(
            1 for pitches in by_onset.values()
            for i, a in enumerate(pitches)
            for b in pitches[i + 1:] if abs(a - b) in (12, 24))
        rate = foreign / total if total else float("nan")
        octave_rate = octaves / len(notes) if notes else float("nan")
        name = f"{track['artist']} - {track['title']}"[:37]
        lines.append(f"{name:38} {total:>7} {rate:>7.1%} {octave_rate:>6.1%}")
        print("\n".join(lines[-1:]), file=sys.stderr)
    print("\n".join(lines), file=sys.stderr)


if __name__ == "__main__":
    main()
