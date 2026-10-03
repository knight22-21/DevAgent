"""Regression tests for the Groq rate limiter's shared token bucket.

The limiter is a module-level singleton (``_groq_limiter``) and workers are
threads that each build their own ``LLMClient`` (see devagent/agent/worker.py),
so ``acquire()`` runs concurrently against one shared bucket. The original
implementation mutated ``tokens`` with no lock, which lets more than one thread
pass the ``tokens >= 1`` check while only a single token is available.

It also waited a full ``1 / fill_rate`` interval per attempt regardless of how
soon the next token was actually due.
"""

import asyncio
import sys
import threading
import time

import pytest

from devagent.core.llm import _TokenBucket


class _Stop(Exception):
    """Raised by the fake sleep so a waiting caller exits immediately."""


def _over_issue_count(trials: int, threads: int) -> int:
    """Count trials where more than one thread acquired with a single token."""
    over = 0
    original_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # widen the check/decrement window for the test
    try:
        for _ in range(trials):
            bucket = _TokenBucket(30)  # fill_rate 0.5 -> 2 s per full interval
            bucket.tokens = 1.0  # exactly one token available
            barrier = threading.Barrier(threads)
            granted: list[int] = []

            def worker(
                _bucket: _TokenBucket = bucket,
                _barrier: threading.Barrier = barrier,
                _granted: list[int] = granted,
            ) -> None:
                _barrier.wait()
                try:
                    _bucket.acquire()
                    _granted.append(1)
                except _Stop:
                    pass

            real_sleep = time.sleep
            time.sleep = lambda _seconds: (_ for _ in ()).throw(_Stop())
            try:
                threads_list = [threading.Thread(target=worker) for _ in range(threads)]
                for t in threads_list:
                    t.start()
                for t in threads_list:
                    t.join()
            finally:
                time.sleep = real_sleep

            if len(granted) > 1:
                over += 1
    finally:
        sys.setswitchinterval(original_interval)
    return over


def _captured_sleeps(fn) -> list[float]:
    """Run *fn*, returning the durations it asked to sleep for."""
    slept: list[float] = []
    real_sleep = time.sleep

    def fake(seconds: float) -> None:
        slept.append(seconds)
        raise _Stop()

    time.sleep = fake  # type: ignore[assignment]
    try:
        fn()
    except _Stop:
        pass
    finally:
        time.sleep = real_sleep
    return slept


def test_acquire_does_not_over_issue_when_workers_race() -> None:
    assert _over_issue_count(trials=200, threads=16) == 0


def test_acquire_returns_without_sleeping_when_a_token_is_available() -> None:
    bucket = _TokenBucket(30)
    bucket.tokens = 1.0

    slept = _captured_sleeps(bucket.acquire)

    assert slept == []
    # one token consumed; the remainder is the sliver refilled before the check
    assert 0.0 <= bucket.tokens < 0.01


def test_acquire_sleeps_only_until_the_next_token_is_due() -> None:
    bucket = _TokenBucket(30)  # fill_rate 0.5
    bucket.tokens = 0.6  # 0.4 tokens short -> 0.8 s, not a full 2.0 s interval

    slept = _captured_sleeps(bucket.acquire)

    assert len(slept) == 1
    assert slept[0] == pytest.approx(0.8, abs=0.05)
    assert slept[0] < 1 / bucket.fill_rate


def test_acquire_serialises_on_the_shared_lock() -> None:
    bucket = _TokenBucket(30)
    bucket.tokens = 1.0
    done = threading.Event()

    def worker() -> None:
        bucket.acquire()
        done.set()

    bucket._tlock.acquire()  # hold the lock on this thread
    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert not done.wait(0.3)  # blocked while the lock is held
    finally:
        bucket._tlock.release()
    assert done.wait(1.0)  # proceeds once the lock is released
    thread.join(1.0)


def test_aacquire_shares_the_same_accounting() -> None:
    bucket = _TokenBucket(30)
    bucket.tokens = 1.0

    asyncio.run(bucket.aacquire())

    assert 0.0 <= bucket.tokens < 0.01


def test_aacquire_waits_only_until_the_next_token_is_due() -> None:
    bucket = _TokenBucket(30)
    bucket.tokens = 0.6
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        raise _Stop()

    asyncio.sleep = fake_sleep  # type: ignore[assignment]
    try:
        with pytest.raises(_Stop):
            asyncio.run(bucket.aacquire())
    finally:
        asyncio.sleep = real_sleep

    assert len(slept) == 1
    assert slept[0] == pytest.approx(0.8, abs=0.05)
