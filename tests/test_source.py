from pathlib import Path

from kord.audio.source import AudioSource, LocalFileAudioSource

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_local_source_matches_by_filename(tmp_path):
    (tmp_path / "Radiohead - Creep.mp3").write_bytes(b"not-real-audio")
    source = LocalFileAudioSource(tmp_path)
    results = source.search("Radiohead", "Creep")
    assert len(results) == 1
    assert results[0].title == "Radiohead - Creep.mp3"


def test_local_source_is_case_insensitive(tmp_path):
    (tmp_path / "RADIOHEAD - creep.mp3").write_bytes(b"x")
    assert len(LocalFileAudioSource(tmp_path).search("radiohead", "CREEP")) == 1


def test_local_source_ignores_non_audio_files(tmp_path):
    (tmp_path / "Radiohead - Creep.txt").write_bytes(b"x")
    assert LocalFileAudioSource(tmp_path).search("Radiohead", "Creep") == []


def test_local_source_returns_empty_when_absent(tmp_path):
    assert LocalFileAudioSource(tmp_path).search("Nobody", "Nothing") == []


def test_local_source_download_returns_existing_path(tmp_path):
    track = tmp_path / "A - B.mp3"
    track.write_bytes(b"x")
    source = LocalFileAudioSource(tmp_path)
    candidate = source.search("A", "B")[0]
    assert source.download(candidate, tmp_path) == track


def test_local_source_satisfies_the_protocol(tmp_path):
    assert isinstance(LocalFileAudioSource(tmp_path), AudioSource)


def test_youtube_source_is_never_imported_by_other_modules():
    """yt-dlp must stay quarantined in exactly one file (global constraint).

    Enforced mechanically rather than by discipline: this is the seam that lets
    the audio provider be swapped by editing a single adapter.

    Only source files count. Compiled bytecode embeds the string too, so once
    the worker has imported the adapter a __pycache__ entry would otherwise
    report a breach that does not exist.
    """
    package = REPO_ROOT / "backend" / "kord"
    hits = sorted(
        str(path.relative_to(REPO_ROOT))
        for path in package.rglob("*.py")
        if "yt_dlp" in path.read_text(encoding="utf-8", errors="ignore")
    )
    assert hits == ["backend/kord/audio/youtube.py"], f"yt-dlp leaked into {hits}"
