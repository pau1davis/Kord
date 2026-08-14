from __future__ import annotations

import logging
import time

from kord import db
from kord.analysis.pipeline import NoAudioFound

log = logging.getLogger("kord.worker")


def _record_retained_audio(conn, pipeline, spotify_id: str) -> None:
    """After a successful run, note what got retained and trim back under cap.

    The pipeline never touches the database — analysis stays decoupled from it
    on purpose — so discovery happens here instead: `AudioStore.path_for` globs
    for whatever the pipeline may have retained, rather than the pipeline
    reporting it directly. Eviction runs right after, so the store can briefly
    overshoot its cap but never stays over it.

    `protect=spotify_id` is load-bearing, not defensive: the track just
    retained has no `last_played_at` yet, which the LRU ordering treats as
    "most evictable" — without the exclusion, eviction would delete the file
    that was just written, every time the store is already at cap. That
    would make the failure permanent: once `audio_dir` reaches its cap, every
    newly analysed song gets retained and immediately deleted, and playback
    404s forever after.

    Never raises: a bookkeeping or eviction failure must not turn a
    successful analysis into a failed job.
    """
    store = getattr(pipeline, "audio_store", None)
    if store is None:
        return
    try:
        path = store.path_for(spotify_id)
        if path is None:
            return
        db.set_audio_ext(conn, spotify_id, path.suffix)
        store.evict_to_fit(conn, incoming_bytes=0, protect=spotify_id)
    except Exception:
        log.warning("could not record/evict retained audio for %s", spotify_id, exc_info=True)


def run_one_job(conn, pipeline) -> str | None:
    """Claim and run a single job. Returns the terminal state, or None if idle.

    Never raises. The worker is a separate process precisely so that an OOM or a
    crash in the analyzer cannot take the API down with it (spec section 10), and
    that guarantee is worthless if exceptions escape this function.
    """
    job = db.claim_job(conn)
    if job is None:
        return None

    track = conn.execute(
        "SELECT * FROM track WHERE spotify_id=?", (job["spotify_id"],)
    ).fetchone()
    if track is None:
        db.finish_job(conn, job["id"], "failed", "track metadata missing")
        return "failed"

    try:
        analysis = pipeline.run(
            track["spotify_id"], track["artist"], track["title"], track["duration_ms"])
    except NoAudioFound as exc:
        # Distinct from a failure: nothing is broken, the audio just isn't findable.
        db.finish_job(conn, job["id"], "unavailable", str(exc))
        return "unavailable"
    except Exception as exc:
        log.exception("analysis failed for %s", job["spotify_id"])
        db.finish_job(conn, job["id"], "failed", f"{type(exc).__name__}: {exc}")
        return "failed"

    db.save_analysis(conn, analysis)
    _record_retained_audio(conn, pipeline, job["spotify_id"])
    db.finish_job(conn, job["id"], "done", None)
    return "done"


def run_one_stem_job(conn, separator, audio_store, stem_store) -> str | None:
    """Separate one queued song. Returns the finished state, or None if idle.

    Separation is a convenience: a failure here records itself and leaves the
    song's analysis and playback completely untouched.
    """
    job = db.claim_stem_job(conn)
    if job is None:
        return None

    spotify_id = job["spotify_id"]
    source = audio_store.path_for(spotify_id)
    if source is None:
        db.finish_stem_job(
            conn, job["id"], "unavailable",
            "no retained audio to separate; re-analyse the song first")
        return "unavailable"

    try:
        separator.separate(source, stem_store.dir_for(spotify_id))
    except Exception as exc:
        # Never leave a half-written set behind: a partial directory would
        # report as "has stems" and play back missing parts.
        stem_store.remove(spotify_id)
        log.warning("stem separation failed for %s", spotify_id, exc_info=True)
        db.finish_stem_job(
            conn, job["id"], "failed", f"{type(exc).__name__}: {exc}")
        return "failed"

    db.finish_stem_job(conn, job["id"], "done")
    return "done"


def worker_loop(
    conn, pipeline, separator=None, stem_store=None, poll_seconds: float = 2.0
) -> None:
    log.info("kord worker started")
    while True:
        # Analysis first: it is what makes a song usable at all, while stems
        # are an extra on top of a song that already works.
        did_work = run_one_job(conn, pipeline) is not None
        if separator is not None and stem_store is not None:
            did_work = run_one_stem_job(
                conn, separator, pipeline.audio_store, stem_store
            ) is not None or did_work
        if not did_work:
            time.sleep(poll_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from kord.analysis.pipeline import AnalysisPipeline
    from kord.audio.stem_store import StemStore
    from kord.audio.stems import DemucsSeparator
    from kord.audio.store import AudioStore
    from kord.audio.youtube import YouTubeAudioSource
    from kord.config import Settings
    from kord.engine import build_recognizer

    settings = Settings.from_env()
    conn = db.connect(settings.db_path)
    db.init_schema(conn)
    recognizer, engine_version = build_recognizer(settings)
    pipeline = AnalysisPipeline(
        source=YouTubeAudioSource(),
        recognizer=recognizer,
        scratch_dir=settings.scratch_dir,
        engine_version=engine_version,
        audio_store=AudioStore(settings.audio_dir, settings.audio_cap_bytes),
    )
    # The separator loads its weights lazily, so a worker that is never asked
    # to separate anything pays nothing for this.
    worker_loop(
        conn, pipeline,
        separator=DemucsSeparator(),
        stem_store=StemStore(settings.stems_dir),
    )


if __name__ == "__main__":
    main()
