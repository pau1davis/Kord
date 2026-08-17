"""Measure transcription accuracy against material whose notes are known.

Synthesised rather than real audio because this is the only source giving
unambiguous per-note truth. Distortion is applied because that is the variable
actually in question — clean guitar is the easy case, and the library this is
for is not clean.
"""
import numpy as np

SR = 22050


def render_riff(notes, distorted, sr=SR):
    """notes: list of (start_s, end_s, midi). Returns (y, sr).

    A stack of harmonics, far closer to a plucked string than a sine, giving
    the transcriber something to fail on honestly.
    """
    total = max(e for _, e, _ in notes) + 0.5
    y = np.zeros(int(total * sr), dtype=np.float32)
    for start, end, midi in notes:
        f = 440.0 * 2 ** ((midi - 69) / 12)
        n = int((end - start) * sr)
        t = np.arange(n) / sr
        voice = sum(np.sin(2 * np.pi * f * h * t) / h for h in range(1, 9))
        # Percussive envelope: a plucked note decays, and onset detectors care.
        voice *= np.exp(-3.0 * t)
        y[int(start * sr):int(start * sr) + n] += voice.astype(np.float32)
    peak = np.abs(y).max()
    if peak > 0:
        y /= peak
    if distorted:
        # Soft clipping, and the compression that follows it in any real rig.
        y = np.tanh(4.0 * y).astype(np.float32)
        y /= np.abs(y).max() or 1.0
    return y, sr


def score(truth, predicted, onset_tolerance_s=0.05):
    """truth/predicted: lists of (start_s, end_s, midi).

    A predicted note matches a true one when the pitch is identical and the
    onset is within tolerance. Each true note is matched at most once, so an
    engine cannot inflate recall by reporting the same note repeatedly.
    """
    unmatched = list(truth)
    matched, octave_errors = 0, 0
    for start, _, midi in predicted:
        hit = next((t for t in unmatched
                    if t[2] == midi and abs(t[0] - start) <= onset_tolerance_s),
                   None)
        if hit is not None:
            unmatched.remove(hit)
            matched += 1
            continue
        if any(abs(t[2] - midi) in (12, 24)
               and abs(t[0] - start) <= onset_tolerance_s for t in truth):
            octave_errors += 1
    onsets = []
    for start, _, midi in predicted:
        near = [t for t in truth if t[2] == midi
                and abs(t[0] - start) <= onset_tolerance_s]
        if near:
            onsets.append(abs(near[0][0] - start) * 1000)
    return {
        "precision": matched / len(predicted) if predicted else 0.0,
        "recall": matched / len(truth) if truth else 0.0,
        "pitch_accuracy": matched / max(1, matched + octave_errors),
        "onset_ms": float(np.median(onsets)) if onsets else float("nan"),
        "octave_error_rate": octave_errors / len(predicted) if predicted else 0.0,
    }


# Three shapes with different failure modes. Single notes are the easy case; a
# power chord is two notes a fifth apart, whose harmonics overlap heavily; a
# full chord is the case polyphonic transcription exists for.
RIFFS = {
    "single_notes": [(i * 0.4, i * 0.4 + 0.35, m) for i, m in
                     enumerate([40, 43, 45, 47, 45, 43, 40, 38])],
    "power_chords": [(i * 0.5 + o, i * 0.5 + 0.45 + o, m + s)
                     for i, m in enumerate([40, 45, 43, 40])
                     for s, o in ((0, 0.0), (7, 0.0))],
    "open_chords": [(i * 0.6, i * 0.6 + 0.55, m) for i, chord in
                    enumerate([(40, 47, 52, 55, 59, 64), (45, 52, 57, 60, 64)])
                    for m in chord],
}


def main():
    import json
    import os
    import tempfile

    import soundfile as sf
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict

    rows = []
    for name, riff in RIFFS.items():
        for distorted in (False, True):
            y, sr = render_riff(riff, distorted)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                sf.write(f.name, y, sr)
                _, _, notes = predict(f.name, ICASSP_2022_MODEL_PATH)
            os.unlink(f.name)
            pred = [(float(n[0]), float(n[1]), int(n[2])) for n in notes]
            rows.append({"riff": name, "distorted": distorted,
                         "n_true": len(riff), "n_pred": len(pred),
                         **score(riff, pred)})

    # To a file, not stdout: basic-pitch prints its own diagnostics to stdout,
    # so anything written there arrives interleaved with them.
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "synth_accuracy.json"
    with open(out, "w") as f:
        json.dump(rows, f, indent=2)
    header = (f"{'riff':14} {'dist':>5} {'true':>5} {'pred':>5} {'prec':>6} "
              f"{'recall':>7} {'pitch':>6} {'onset':>7} {'octerr':>7}")
    lines = [header]
    for r in rows:
        lines.append(
            f"{r['riff']:14} {str(r['distorted']):>5} {r['n_true']:>5} "
            f"{r['n_pred']:>5} {r['precision']:>6.2f} {r['recall']:>7.2f} "
            f"{r['pitch_accuracy']:>6.2f} {r['onset_ms']:>6.1f}m "
            f"{r['octave_error_rate']:>7.2f}")
    print("\n".join(lines), file=sys.stderr)


if __name__ == "__main__":
    main()
