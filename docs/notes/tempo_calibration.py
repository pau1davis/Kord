"""Print the double-time discriminator's inputs for songs of known tempo.

Throwaway measurement script, kept next to its note. Run:

    .venv/bin/python docs/notes/tempo_calibration.py
"""
import pathlib
import sys
import tempfile

import librosa
import numpy as np

sys.path.insert(0, "backend")
from kord.audio.decode import decode_to_wav  # noqa: E402
from kord.audio.validate import rank_candidates  # noqa: E402
from kord.audio.youtube import YouTubeAudioSource  # noqa: E402

# (artist, title, true_bpm, approx_duration_ms) — true_bpm from a trusted
# source or by ear, NOT from Kord.
SONGS = [
    ("Marvin Gaye", "Mercy Mercy Me", 93, 193_600),
    ("Pantera", "Mouth for War", 91, 237_346),
    ("Ramones", "Blitzkrieg Bop", 177, 132_000),
    ("Slayer", "Raining Blood", 212, 257_000),
    ("Chief Keef", "Love Sosa", 125, 232_000),
    ("Dinosaur Jr.", "The Wagon", 148, 190_000),
    ("My Bloody Valentine", "Only Shallow", 108, 257_000),
]


def measure(y, sr, fmax=None):
    tempo, frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    tempo = float(np.atleast_1d(tempo)[0])
    kwargs = {"fmax": fmax} if fmax else {}
    env = librosa.onset.onset_strength(y=y, sr=sr, **kwargs)
    st = env[np.clip(frames, 0, len(env) - 1)]
    even, odd = st[0::2].mean(), st[1::2].mean()
    strong, weak = max(even, odd), min(even, odd)
    return tempo, (weak / strong if strong > 0 else 1.0)


def main():
    src = YouTubeAudioSource()
    header = (f"{'song':38} {'true':>5} {'librosa':>8} {'/2':>6} "
              f"{'ratio':>6} {'lowband':>8}  verdict")
    print(header)
    print("-" * len(header))

    for artist, title, true_bpm, duration_ms in SONGS:
        ranked = rank_candidates(duration_ms, src.search(artist, title))
        work = pathlib.Path(tempfile.mkdtemp())
        wav = None
        for cand, _tier, _ratio in ranked:
            try:
                wav = decode_to_wav(src.download(cand, work), work / "x.wav")
                break
            except Exception:
                continue
        label = f"{artist} - {title}"
        if wav is None:
            print(f"{label:38} {true_bpm:5}   download failed")
            continue

        y, sr = librosa.load(wav, sr=22050, mono=True)
        tempo, ratio = measure(y, sr)
        _, low_ratio = measure(y, sr, fmax=200.0)

        # Does the reported tempo need halving to match the truth?
        needs_halving = abs(tempo / 2 - true_bpm) < abs(tempo - true_bpm)
        verdict = "NEEDS HALVING" if needs_halving else "correct as-is"
        print(f"{label:38} {true_bpm:5} {tempo:8.1f} {tempo / 2:6.1f} "
              f"{ratio:6.3f} {low_ratio:8.3f}  {verdict}")


if __name__ == "__main__":
    main()
