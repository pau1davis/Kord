"""The ONLY module permitted to import yt-dlp.

Kord is a personal, single-user tool. This adapter sits behind the AudioSource
seam so the dependency can be removed or replaced by editing exactly one file —
enforced by a test in tests/test_source.py, not by discipline.
"""
from __future__ import annotations

from pathlib import Path

import yt_dlp

from kord.models import AudioCandidate


class YouTubeAudioSource:
    def __init__(self, max_results: int = 5) -> None:
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
            )
            for entry in (info.get("entries") or [])
        ]

    def download(self, candidate: AudioCandidate, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        template = str(dest_dir / "%(id)s.%(ext)s")
        options = {
            "quiet": True, "no_warnings": True, "format": "bestaudio/best",
            "outtmpl": template, "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(candidate.url, download=True)
            return Path(ydl.prepare_filename(info))
