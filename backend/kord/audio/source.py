from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from kord.models import AudioCandidate


@runtime_checkable
class AudioSource(Protocol):
    """The only seam through which Kord obtains analyzable audio.

    Spotify supplies no audio at all (spec section 2.2), so every provider sits
    behind this interface. Swapping providers means writing one adapter; nothing
    downstream knows or cares where the bytes came from.
    """

    def search(self, artist: str, title: str) -> list[AudioCandidate]: ...

    def download(self, candidate: AudioCandidate, dest_dir: Path) -> Path: ...


class LocalFileAudioSource:
    """Audio from files you already own. Used in tests and as a legitimate provider."""

    SUFFIXES = (".mp3", ".flac", ".m4a", ".wav", ".ogg")

    def __init__(self, library_dir: Path) -> None:
        self.library_dir = Path(library_dir)

    def search(self, artist: str, title: str) -> list[AudioCandidate]:
        needle_artist, needle_title = artist.lower(), title.lower()
        results: list[AudioCandidate] = []
        for path in sorted(self.library_dir.iterdir()):
            if path.suffix.lower() not in self.SUFFIXES:
                continue
            name = path.name.lower()
            if needle_artist in name and needle_title in name:
                results.append(AudioCandidate(
                    path=str(path), url=path.as_uri(), duration_ms=0, title=path.name))
        return results

    def download(self, candidate: AudioCandidate, dest_dir: Path) -> Path:
        return Path(candidate.path)
