import pytest

from kord.audio.throttle import Throttle, looks_refused


class FakeTime:
    """A clock that only moves when something sleeps."""

    def __init__(self):
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def throttle(**kwargs):
    fake = FakeTime()
    return Throttle(clock=fake.clock, sleeper=fake.sleep, **kwargs), fake


def test_the_first_request_is_not_delayed():
    t, fake = throttle(min_interval_s=8.0)
    assert t.wait() == 0.0
    assert fake.slept == []


def test_the_next_request_waits_the_interval():
    t, fake = throttle(min_interval_s=8.0)
    t.wait()
    assert t.wait() == pytest.approx(8.0)


def test_a_slow_request_does_not_earn_the_next_one_a_free_pass():
    """The interval is booked from when a request starts, so a download that
    took a minute does not license an immediate follow-up."""
    t, fake = throttle(min_interval_s=8.0)
    t.wait()
    fake.now += 60.0          # the download itself took a while
    assert t.wait() == 0.0    # that one is due
    assert t.wait() == pytest.approx(8.0)   # but the one after still waits


def test_a_refusal_makes_the_next_request_wait_much_longer():
    t, _ = throttle(min_interval_s=8.0, backoff_start_s=60.0)
    t.wait()
    t.refused()
    assert t.wait() == pytest.approx(68.0)


def test_refusals_stack_up_rather_than_repeating_the_same_delay():
    # Being turned away twice means backing off harder, not identically.
    t, _ = throttle(min_interval_s=0.0, backoff_start_s=60.0)
    t.wait(); t.refused()
    t.wait(); t.refused()
    assert t.penalty_s == pytest.approx(120.0)
    t.refused()
    assert t.penalty_s == pytest.approx(240.0)


def test_the_backoff_stops_growing_at_the_cap():
    t, _ = throttle(backoff_start_s=60.0, backoff_max_s=200.0)
    for _ in range(10):
        t.refused()
    assert t.penalty_s == pytest.approx(200.0)


def test_success_clears_the_penalty():
    t, _ = throttle(min_interval_s=8.0, backoff_start_s=60.0)
    t.refused()
    t.succeeded()
    t.wait()
    assert t.wait() == pytest.approx(8.0)


class TestLooksRefused:
    def test_the_403_that_actually_happened(self):
        assert looks_refused(Exception(
            "ERROR: unable to download video data: HTTP Error 403: Forbidden"))

    def test_other_ways_a_provider_says_no(self):
        assert looks_refused(Exception("HTTP Error 429: Too Many Requests"))
        assert looks_refused(Exception("Sign in to confirm you're not a bot"))

    def test_a_genuinely_missing_video_is_not_a_refusal(self):
        # Backing off for fifteen minutes because one video was deleted would
        # stall the queue for no reason.
        assert not looks_refused(Exception(
            "ERROR: [youtube] bVPhmP8Lli8: This video is not available"))
        assert not looks_refused(Exception("Private video"))

    def test_an_age_gate_is_not_rate_limiting(self):
        assert not looks_refused(Exception(
            "Sign in to confirm your age. This video may be inappropriate"))
