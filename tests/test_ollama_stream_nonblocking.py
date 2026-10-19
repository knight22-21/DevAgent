"""Issue #103: ``_ollama_stream()`` must not block the event loop.

The stream used to iterate a *synchronous* ``ollama.Client.chat()`` generator
inside an ``async def``, so every network read froze the loop for the length of
that read.  An ``async def`` wrapper makes a generator awaitable; it does not
make a blocking read concurrent.

The first test drives the stream with a fake client whose per-chunk delay
stands in for a network read, and measures whether a coroutine sharing the
loop still gets to run.  The second pins the chunk contract so the fix cannot
change what callers receive.  No Ollama server is contacted.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from devagent.core.config import LLMConfig
from devagent.core.llm import AgentMessage, LLMClient

CHUNKS = ("part0", "part1", "part2")
CHUNK_DELAY = 0.05
TICK = 0.01


def _chunk(text: str) -> SimpleNamespace:
    return SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=[]))


class _SlowSyncClient:
    """A stand-in for ``ollama.Client``: blocking reads between chunks."""

    def __init__(self, delay: float = CHUNK_DELAY) -> None:
        self.delay = delay

    def chat(self, **_kwargs):
        for text in CHUNKS:
            time.sleep(self.delay)
            yield _chunk(text)


class _SlowAsyncClient:
    """A stand-in for ``ollama.AsyncClient``: the same reads, awaited."""

    def __init__(self, delay: float = CHUNK_DELAY) -> None:
        self.delay = delay

    async def chat(self, **_kwargs):
        async def _gen():
            for text in CHUNKS:
                await asyncio.sleep(self.delay)
                yield _chunk(text)

        return _gen()


class _MixedSyncClient:
    """Sync client yielding empty content, to pin the chunk contract."""

    def chat(self, **_kwargs):
        for text in ("a", "", "b"):
            yield _chunk(text)


class _MixedAsyncClient:
    """Async twin of :class:`_MixedSyncClient`."""

    async def chat(self, **_kwargs):
        async def _gen():
            for text in ("a", "", "b"):
                await asyncio.sleep(0)
                yield _chunk(text)

        return _gen()


def _client() -> LLMClient:
    return LLMClient(LLMConfig(provider="ollama", model="qwen2.5-coder:7b"))


def _patch_clients(
    monkeypatch: pytest.MonkeyPatch, sync_client, async_client
) -> None:
    """Point both client factories at fakes, whichever one the code reaches for."""
    monkeypatch.setattr(LLMClient, "_ollama_client", lambda self: sync_client)
    monkeypatch.setattr(
        LLMClient, "_ollama_async_client", lambda self: async_client, raising=False
    )


async def _consume_with_ticker(llm: LLMClient) -> tuple[list[str], int]:
    """Consume the stream while a second coroutine counts its turns."""
    ticks = 0
    done = False

    async def ticker() -> None:
        nonlocal ticks
        while not done:
            ticks += 1
            await asyncio.sleep(TICK)

    task = asyncio.create_task(ticker())
    parts = [
        text
        async for text in llm._ollama_stream([AgentMessage(role="user", content="hi")])
    ]
    done = True
    await task
    return parts, ticks


async def test_ollama_stream_leaves_the_event_loop_responsive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A coroutine on the same loop keeps running while the stream is consumed."""
    _patch_clients(monkeypatch, _SlowSyncClient(), _SlowAsyncClient())

    parts, ticks = await _consume_with_ticker(_client())

    assert parts == list(CHUNKS)
    # Streaming takes ~0.15s and the ticker runs every 0.01s, so a free loop
    # gives double-digit turns. A loop that is blocked by the sync reads gives
    # zero -- the ticker is created but never scheduled.
    assert ticks >= 3, f"event loop was blocked during the stream ({ticks} ticks)"


async def test_ollama_stream_yields_every_non_empty_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The chunk contract is unchanged: text in order, empty content dropped."""
    _patch_clients(monkeypatch, _MixedSyncClient(), _MixedAsyncClient())

    parts = [
        text
        async for text in _client()._ollama_stream(
            [AgentMessage(role="user", content="hi")]
        )
    ]

    assert parts == ["a", "b"]
