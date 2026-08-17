"""What the uploader's title says about a candidate recording.

Duration matching (`validate.classify_ratio`) catches recordings of obviously
the wrong length, but a live take played at close to the record's tempo lands
inside the 2% band and passes, and nothing about a length distinguishes a music
video from a plain audio upload. Both matter: a live arrangement has different
chords, a different tempo and often a different key, so analysing one produces
confidently wrong theory rather than no theory.

The signal is the text the uploader added *around* the song — so this strips the
artist and song name out first. Otherwise "Live and Let Die" reads as a concert
recording and "Alive" nearly does too.
"""
from __future__ import annotations

import re

# A different performance, arrangement or player. Analysing one of these gives
# the wrong answer for the record the user asked about.
REJECT = (
    r"live", r"concert", r"unplugged", r"session", r"rehearsal", r"soundcheck",
    r"cover", r"covered by", r"karaoke", r"instrumental", r"backing track",
    r"acoustic", r"demo", r"remix", r"remixed", r"mashup", r"bootleg",
    r"lesson", r"tutorial", r"how to play", r"tabs?", r"play ?along",
    r"reaction", r"reacts",
    # Doctored uploads: the pitch or tempo is no longer the record's.
    r"sped up", r"speed up", r"slowed", r"nightcore", r"reverb", r"8d",
    r"bass boosted", r"extended", r"medley", r"megamix", r"loop(ed)?",
    r"full album", r"\d+ hours?",
)

# The distributor's own audio, with no film attached.
PREFERRED = (r"official audio", r"audio only", r"full audio", r"visuali[sz]er")

# Usually the album audio, but sometimes with a film intro or dialogue over it.
VIDEO = (r"official video", r"music video", r"official hd video")

_REJECT_RE = re.compile(r"\b(?:%s)\b" % "|".join(REJECT))
_PREFERRED_RE = re.compile(r"\b(?:%s)\b" % "|".join(PREFERRED))
_VIDEO_RE = re.compile(r"\b(?:%s)\b" % "|".join(VIDEO))


def normalise(text: str) -> str:
    """Lowercase, punctuation to spaces, runs of space collapsed.

    Uploaders separate words with anything at hand — "Mercy, Mercy Me",
    "Marvin Gaye...Mercy Mercy Me...", "[slowed + reverb]" — so matching has to
    happen on the words alone.
    """
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _strip(haystack: str, phrase: str) -> str:
    """Remove a phrase, on word boundaries so "Live" never eats "Alive"."""
    if not phrase:
        return haystack
    return " ".join(
        re.sub(rf"\b{re.escape(phrase)}\b", " ", haystack).split())


def classify_title(
    candidate_title: str, artist: str = "", title: str = "", *, uploader: str = "",
) -> str:
    """One of "reject", "video", "ok" or "preferred"."""
    extra = _strip(_strip(normalise(candidate_title), normalise(title)),
                   normalise(artist))
    if _REJECT_RE.search(extra):
        return "reject"
    # YouTube's auto-generated "<artist> - Topic" channels are the label's own
    # upload of the master: the closest thing available to the record itself.
    if normalise(uploader).endswith(" topic"):
        return "preferred"
    if _PREFERRED_RE.search(extra):
        return "preferred"
    if _VIDEO_RE.search(extra):
        return "video"
    return "ok"
