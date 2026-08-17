# Tempo double-time calibration — 2026-08-13

Measured with `tempo_calibration.py` in this directory. `true` is from a
trusted source or by ear, never from Kord. `ratio` is the weaker beat phase's
mean onset strength over the stronger one — the discriminator's input.

| song | true | librosa | halved | ratio | low-band | needs halving? |
|---|---|---|---|---|---|---|
| Marvin Gaye — Mercy Mercy Me | 93 | 184.6 | 92.3 | **0.698** | 0.682 | yes — true octave error |
| My Bloody Valentine — Only Shallow | 108 | 172.3 | 86.1 | 0.856 | 0.817 | no — see below |
| Pantera — Mouth for War | 91 | 103.4 | 51.7 | 0.973 | 0.963 | no |
| Ramones — Blitzkrieg Bop | 177 | 89.1 / 99.4 | — | 0.770 / 0.917 | 0.788 / 0.904 | no — under-reported |
| Slayer — Raining Blood | 212 | 89.1 | — | 0.842 | 0.999 | no — under-reported |
| Chief Keef — Love Sosa | 125 | download failed | | | | |
| Dinosaur Jr. — The Wagon | 148 | download failed | | | | |

Blitzkrieg Bop appears twice because two different candidates were downloaded
across runs; the tempo estimate differs by upload, which is itself worth
knowing.

## Chosen values

```python
DOUBLE_TIME_FLOOR_BPM = 130.0
PHASE_MARGIN = 0.85
```

Full-spectrum onset envelope. Unchanged from the provisional values — the
measurement confirmed them rather than moved them.

Only two songs in the set clear the 130 floor and are therefore candidates at
all: Mercy Mercy Me (0.698, halved — correct) and Only Shallow (0.856, left
alone — correct, see below). Everything else is below the floor and untouched
regardless of its ratio.

## The low-band discriminator is rejected

The plan offered `onset_strength(..., fmax=200.0)` as a fallback if the groups
failed to separate. The data says do not use it.

Low-band pulls Only Shallow to 0.817, under the threshold, so it would be
halved from 172.3 to 86.1. Its true tempo is ~108. **Halving makes that song
worse, not better** — 172.3 and 86.1 are both wrong, and the error is not an
octave relationship at all (108 doubled is 216, halved is 54). librosa is
simply mis-locking on this track in a way no octave correction can fix.

Full-spectrum leaves it at 0.856, just above the threshold, and therefore
alone. That is the correct outcome for the right reason: when the error is not
an octave error, the octave correction should decline to act.

## Known wrong, recorded deliberately

**Fast music is under-reported, and this correction does not address it.**
Blitzkrieg Bop (true 177) comes back at 89–99, and Raining Blood (true 212) at
89.1. librosa mis-locks *downward* on fast punk and thrash, roughly halving
them. This work only ever halves a tempo, so it cannot help here and does not
try — both sit below the 130 floor and are passed through untouched.

For a user who plays this music, Kord will still show roughly half the true
tempo on fast tracks. Fixing it needs the opposite correction (doubling on
evidence of missed beats between detected ones), which is a separate piece of
work with its own confounds — a genuine half-time feel is common and must not
be doubled away.

**Only Shallow is still wrong**, reported at 172.3 against a true ~108. Left
alone rather than made differently wrong.

## Calibration gap

No genuinely fast song *above* the 130 floor was obtained. Love Sosa (125) and
The Wagon (148) both failed to download across repeated attempts, and The
Wagon was the control that mattered most: at a true 148 with a strong
backbeat, it is exactly the shape that could be wrongly halved to 74.

So the backbeat confound described in `correct_double_time`'s docstring
remains **measured on zero counter-examples**. The floor and margin are set
conservatively for that reason. If a song ever shows up reported at half its
true tempo after this change, this is the first place to look, and the fix is
to raise `PHASE_MARGIN` toward 0.7 so only a stark asymmetry acts.

---

## 2026-08-17 — the doubling correction was attempted and abandoned

The section above said fixing under-reported fast music "needs the opposite
correction (doubling on evidence of missed beats between detected ones)" and
flagged the confound: a genuine half-time feel must not be doubled away. The
obvious discriminator was measured across all 57 analysed songs and does not
work.

**Method.** For each song, mean onset strength halfway between detected beats,
divided by mean onset strength on the beats. The hypothesis: where the tracker
locked onto half the true tempo, the midpoints carry real beats and the ratio
is high; where the tempo is right, midpoints carry only subdivisions and the
ratio is low.

**Result.** The bands do not separate, and the sign is backwards.

| reported tempo | n | median ratio | range |
|---|---|---|---|
| under 78 BPM (suspect half-time) | 16 | **0.84** | 0.38–2.88 |
| 78–110 (probably correct) | 21 | **1.04** | 0.16–1.62 |
| 110 and above (cannot be half-time) | 20 | **0.96** | 0.18–2.99 |

The songs most likely to be half-time detections have the *lowest* midpoint
energy, not the highest, and all three ranges overlap almost entirely. At a
threshold of 0.9 the rule would double 11 of the 20 songs that are already fast
— including Fade To Black, from about 113 to about 226.

**Why the confound is fatal.** Most rock plays the eighths on guitar or hi-hat,
so midpoint energy is present whether or not the tempo is wrong. The
measurement cannot tell "a beat the tracker missed" from "a subdivision that
was always there", because acoustically they are the same event.

**Not built.** Doubling on this signal would make more songs wrong than it
fixed, which is worse than the current state where fast songs are consistently
under-reported.

**What could work instead**, in rough order of cost:

1. **Let the player halve or double it.** A control that persists the choice
   per song. Cannot be wrong, since the human knows the song, and it is the
   judgement machines are worst at. Also fixes Only Shallow, which is not an
   octave error and no correction can reach.
2. **Show the alternative** — "68 BPM (or 136)" — so the ambiguity is visible
   rather than a confident wrong number.
3. **Track beats on the isolated drum stem.** A far better signal than a full
   mix, but stems are produced on demand after analysis, so tempo would have to
   be revised later rather than measured once.
