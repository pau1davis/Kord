"""The ONLY module permitted to import yt-dlp.

Kord is a personal, single-user tool. This adapter sits behind the AudioSource
seam so the dependency can be removed or replaced by editing exactly one file —
enforced by a test in tests/test_source.py, not by discipline.
"""
from __future__ import annotations

from pathlib import Path

import yt_dlp

from kord.models import AudioCandidate

# m4a first: YouTube's WebM/Opus carries no seek index and no stream duration,
# which breaks seeking, is refused outright by Safari, and is a poor input to
# stem separation. The fallback keeps songs offering no m4a working.
DOWNLOAD_FORMAT = "bestaudio[ext=m4a]/bestaudio/best"


class YouTubeAudioSource:
    # Wider than it needs to be for one good result. Live takes, covers,
    # lessons and reaction videos all rank highly for a well known song, and
    # they are all discarded before a download is attempted (validate.py), so
    # a narrow search can come back with nothing usable at all.
    def __init__(self, max_results: int = 12) -> None:
        self.max_results = max_results

    def search(self, artist: str, title: str) -> list[AudioCandidate]:
        query = f"ytsearch{self.max_results}:{artist} {title}"
        options = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "extract_flat": False, "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(query, download=False)
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
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(candidate.url, download=True)
            return Path(ydl.prepare_filename(info))
