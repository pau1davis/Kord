"""The ONLY module permitted to import yt-dlp.

Kord is a personal, single-user tool. This adapter sits behind the AudioSource
seam so the dependency can be removed or replaced by editing exactly one file —
enforced by a test in tests/test_source.py, not by discipline.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yt_dlp

from kord.audio.throttle import Throttle, looks_refused
from kord.models import AudioCandidate

# m4a first: YouTube's WebM/Opus carries no seek index and no stream duration,
# which breaks seeking, is refused outright by Safari, and is a poor input to
# stem separation. The fallback keeps songs offering no m4a working.
DOWNLOAD_FORMAT = "bestaudio[ext=m4a]/bestaudio/best"

# Which of YouTube's own players to impersonate when fetching stream URLs.
#
# As of 2026-08-18 the default client answers HTTP 403 for the audio stream on
# every video tried, while `android` downloads the same video without
# complaint. This looked exactly like rate limiting — every candidate for every
# song refused — and was not: it survived eighteen hours of not asking, and one
# client switch fixed it immediately.
#
# A list rather than a pin, because YouTube breaks these in rotation and
# yt-dlp falls through to the next. Ordered by what currently works.
PLAYER_CLIENTS = ("android", "web_safari", "web")

log = logging.getLogger("kord.youtube")


class YouTubeAudioSource:
    # Wider than it needs to be for one good result. Live takes, covers,
    # lessons and reaction videos all rank highly for a well known song, and
    # they are all discarded before a download is attempted (validate.py), so
    # a narrow search can come back with nothing usable at all.
    def __init__(self, max_results: int = 12, throttle: Throttle | None = None) -> None:
        self.max_results = max_results
        # One throttle across searches and downloads, because YouTube counts
        # them against the same caller. Held on the instance so the worker's
        # single source paces the whole queue, not each song in isolation.
        self.throttle = throttle or Throttle()

    def _guarded(self, call):
        """Pace a call, and back off harder if we are being turned away."""
        self.throttle.wait()
        try:
            result = call()
        except Exception as error:
            if looks_refused(error):
                self.throttle.refused()
                log.warning(
                    "provider refused us; next request held for %.0fs",
                    self.throttle.penalty_s)
            raise
        self.throttle.succeeded()
        return result

    def search(self, artist: str, title: str) -> list[AudioCandidate]:
        query = f"ytsearch{self.max_results}:{artist} {title}"
        options = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "extract_flat": False, "noplaylist": True,
        }
        def run():
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(query, download=False)

        info = self._guarded(run)
        return [
            AudioCandidate(
                path=None,
                url=entry.get("webpage_url") or entry["url"],
                duration_ms=int((entry.get("duration") or 0) * 1000),
                title=entry.get("title", ""),
                uploader=entry.get("uploader") or entry.get("channel") or "",
            )
            for entry in (info.get("entries") or [])
        ]

    def download(self, candidate: AudioCandidate, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        template = str(dest_dir / "%(id)s.%(ext)s")
        options = {
            "quiet": True, "no_warnings": True, "format": DOWNLOAD_FORMAT,
            "outtmpl": template, "noplaylist": True,
            "extractor_args": {"youtube": {"player_client": list(PLAYER_CLIENTS)}},
        }
        def run():
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(candidate.url, download=True)
                return Path(ydl.prepare_filename(info))

        return self._guarded(run)
