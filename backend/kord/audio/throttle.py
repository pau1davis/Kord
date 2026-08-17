"""Pacing for requests to a provider that will start refusing us.

Kord analyses a library in the background, and nothing stopped it asking
YouTube for song after song as fast as it could decode them. Re-analysing 57
songs after an engine bump was enough to get every download refused with HTTP
403 — not for one video, for all of them, which is the shape of rate limiting
rather than a missing file.

Time is injected so the policy can be tested without waiting for it.
"""
from __future__ import annotations

import time
from collections.abc import Callable

# Polite for a personal tool working through a library in the background, and
# far below what took an hour to get blocked.
MIN_INTERVAL_S = 8.0
# First penalty after a refusal, doubling each time.
BACKOFF_START_S = 60.0
BACKOFF_MAX_S = 900.0


class Throttle:
    def __init__(
        self,
        min_interval_s: float = MIN_INTERVAL_S,
        backoff_start_s: float = BACKOFF_START_S,
        backoff_max_s: float = BACKOFF_MAX_S,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval_s = min_interval_s
        self.backoff_start_s = backoff_start_s
        self.backoff_max_s = backoff_max_s
        self._clock = clock
        self._sleep = sleeper
        self._next_allowed = 0.0
        self._penalty = 0.0

    @property
    def penalty_s(self) -> float:
        """How long the next request will be held back beyond the interval."""
        return self._penalty

    def wait(self) -> float:
        """Block until the next request is allowed. Returns seconds waited."""
        delay = max(0.0, self._next_allowed - self._clock())
        if delay > 0:
            self._sleep(delay)
        # Booked from now rather than from the previous slot, so a slow request
        # does not earn the next one a free pass.
        self._next_allowed = self._clock() + self.min_interval_s + self._penalty
        return delay

    def succeeded(self) -> None:
        """Clear the penalty — whatever we were being punished for is over."""
        self._penalty = 0.0

    def refused(self) -> None:
        """Called after a refusal. Doubles the penalty, up to the cap.

        The next slot is pushed out here rather than left to the next `wait`:
        that slot was booked before the refusal happened, so without this the
        penalty would skip the very request it exists to hold back.
        """
        self._penalty = min(
            self.backoff_max_s,
            self.backoff_start_s if self._penalty == 0 else self._penalty * 2)
        self._next_allowed = max(
            self._next_allowed,
            self._clock() + self.min_interval_s + self._penalty)


def looks_refused(error: BaseException) -> bool:
    """Is this the provider turning us away rather than a bad video?

    Matched on the message because yt-dlp wraps everything in DownloadError
    without a status code. Crude, and deliberately narrow: a false positive
    only costs a slower next request, while a false negative keeps hammering a
    provider that has already said no.
    """
    text = str(error).lower()
    return any(marker in text for marker in (
        "403", "forbidden", "429", "too many requests", "rate limit",
        "sign in to confirm you're not a bot",
    ))
