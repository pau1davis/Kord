from pathlib import Path

import pytest

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


def test_download_format_prefers_m4a_with_a_fallback():
    """WebM/Opus from YouTube carries no seek index and no stream duration,
    which breaks seeking and Safari. m4a has both. The fallback keeps songs
    that offer no m4a working rather than failing them."""
    from kord.audio.youtube import DOWNLOAD_FORMAT

    assert DOWNLOAD_FORMAT.startswith("bestaudio[ext=m4a]")
    assert "/bestaudio" in DOWNLOAD_FORMAT


def test_the_youtube_source_paces_its_requests_and_backs_off():
    """The failure this prevents: re-analysing a library queued download after
    download until YouTube refused every one of them with HTTP 403.

    Exercised through the source's own guard rather than the network, so it
    asserts the pacing without waiting for it or asking YouTube for anything.
    """
    from kord.audio.throttle import Throttle
    from kord.audio.youtube import YouTubeAudioSource

    waits, slept = [], []
    now = [0.0]

    def sleeper(seconds):
        slept.append(seconds)
        now[0] += seconds

    throttle = Throttle(min_interval_s=8.0, backoff_start_s=60.0,
                        clock=lambda: now[0], sleeper=sleeper)
    source = YouTubeAudioSource(throttle=throttle)

    # Three ordinary calls: the first goes straight through, the rest are paced.
    for _ in range(3):
        waits.append(source._guarded(lambda: "ok"))
    assert slept == [pytest.approx(8.0), pytest.approx(8.0)]

    # A refusal holds the next request far longer than the interval.
    with pytest.raises(RuntimeError):
        source._guarded(lambda: (_ for _ in ()).throw(
            RuntimeError("HTTP Error 403: Forbidden")))
    assert throttle.penalty_s == pytest.approx(60.0)
    source._guarded(lambda: "ok")
    assert slept[-1] == pytest.approx(68.0)

    # ...and success clears it, so one bad video does not slow everything after.
    assert throttle.penalty_s == 0.0


def test_a_missing_video_does_not_trigger_a_backoff():
    """Backing off fifteen minutes because one video was deleted would stall
    the whole queue for a reason that has nothing to do with rate limiting."""
    from kord.audio.throttle import Throttle
    from kord.audio.youtube import YouTubeAudioSource

    throttle = Throttle(clock=lambda: 0.0, sleeper=lambda _s: None)
    source = YouTubeAudioSource(throttle=throttle)
    with pytest.raises(RuntimeError):
        source._guarded(lambda: (_ for _ in ()).throw(
            RuntimeError("ERROR: [youtube] abc: This video is not available")))
    assert throttle.penalty_s == 0.0
