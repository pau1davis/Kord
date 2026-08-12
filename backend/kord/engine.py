"""Which chord engine is in play, resolved identically everywhere.

The worker writes analyses stamped with an engine version and the API reads them
back by that same key. If the two disagreed, every cache lookup would miss in
silence and songs would re-analyze forever — so both call in here rather than
deciding for themselves.
"""
from __future__ import annotations

import logging
import os

from kord.config import Settings

log = logging.getLogger("kord.engine")

BTC_VERSION = "btc-2"      # btc-2 adds the heaviness score
CHROMA_VERSION = "chroma-1"


def weights_path(settings: Settings):
    from kord.analysis.btc import WEIGHTS_FILENAME
    return settings.model_dir / WEIGHTS_FILENAME


def resolve_engine_version(settings: Settings) -> str:
    """Prefer the deep engine when its weights are present.

    An explicit KORD_ENGINE_VERSION always wins, so a stale cache can be pinned
    or replayed deliberately.
    """
    if os.environ.get("KORD_ENGINE_VERSION"):
        return settings.engine_version
    return BTC_VERSION if weights_path(settings).exists() else CHROMA_VERSION


def build_recognizer(settings: Settings):
    """Return (recognizer, engine_version) consistent with resolve_engine_version."""
    from kord.analysis.btc import BtcChordRecognizer
    from kord.analysis.recognizer import ChromaTemplateRecognizer

    version = resolve_engine_version(settings)
    if version == BTC_VERSION:
        path = weights_path(settings)
        if not path.exists():
            raise FileNotFoundError(
                f"KORD_ENGINE_VERSION pins {BTC_VERSION} but weights are missing at "
                f"{path}. Fetch them with: python -m kord.analysis.btc --fetch-weights"
            )
        log.info("using BTC large-vocabulary recognizer")
        return BtcChordRecognizer(path), version

    log.warning(
        "using the chroma baseline (major/minor triads only). For the full chord "
        "vocabulary run: python -m kord.analysis.btc --fetch-weights")
    return ChromaTemplateRecognizer(), version
