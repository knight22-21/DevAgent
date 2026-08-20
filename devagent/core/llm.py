"""LLM provider factory — direct official SDKs, no framework wrapper.

Returns a unified LLMClient that the agent loop calls for completions.
Supports: ollama, anthropic, openai, groq (openai-compatible), gemini.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Iterator

from devagent.core.config import DevAgentConfig, LLMConfig


@dataclass
class Message:
    role: str   # "system" | "user" | "assistant" | "tool"
    content: str


@dataclass
class LLMResponse:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    provider: str = ""


class TokenBucket:
    """Simple token-bucket rate limiter (kept for Groq free-tier)."""

    def __init__(self, tokens_per_minute: int):
        self.capacity = tokens_per_minute
        self.tokens = float(tokens_per_minute)
        self.fill_rate = tokens_per_minute / 60.0
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    def _update(self) -> None:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.last_update) * self.fill_rate)
        self.last_update = now

    def acquire(self) -> None:
        while True:
            self._update()
            if self.tokens >= 1:
                self.tokens -= 1
                return
            time.sleep(1 / self.fill_rate)

    async def aacquire(self) -> None:
        while True:
            async with self._lock:
                self._update()
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
            await asyncio.sleep(1 / self.fill_rate)


_groq_limiter = TokenBucket(30)


class LLMClient:
    """Unified LLM client over official provider SDKs."""

    def __init__(self, cfg: LLMConfig) -> None:
        self.cfg = cfg

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def complete(self, messages: list[Message], **kwargs) -> LLMResponse:
        """Synchronous completion."""
        provider = self.cfg.provider
        if provider == "ollama":
            return self._ollama(messages, **kwargs)
        elif provider in ("openai", "groq"):
            return self._openai_compat(messages, **kwargs)
        elif provider == "anthropic":
            return self._anthropic(messages, **kwargs)
        elif provider == "gemini":
            return self._gemini(messages, **kwargs)
        else:
            raise ValueError(f"Unknown provider: {provider!r}")

    async def acomplete(self, messages: list[Message], **kwargs) -> LLMResponse:
        """Async completion (runs sync call in thread to avoid blocking)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.complete(messages, **kwargs))

    async def astream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]:
        """Async streaming — yields text chunks as they arrive."""
        provider = self.cfg.provider
        if provider == "ollama":
            async for chunk in self._ollama_stream(messages, **kwargs):
                yield chunk
        elif provider in ("openai", "groq"):
            async for chunk in self._openai_stream(messages, **kwargs):
                yield chunk
        elif provider == "anthropic":
            async for chunk in self._anthropic_stream(messages, **kwargs):
                yield chunk
        elif provider == "gemini":
            # Gemini streaming via run_in_executor (SDK is sync-first)
            response = await self.acomplete(messages, **kwargs)
            yield response.content
        else:
            raise ValueError(f"Unknown provider: {provider!r}")

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _ollama(self, messages: list[Message], **kwargs) -> LLMResponse:
        import ollama
        resp = ollama.chat(
            model=self.cfg.model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            options={"temperature": self.cfg.temperature},
        )
        return LLMResponse(
            content=resp.message.content,
            input_tokens=resp.prompt_eval_count or 0,
            output_tokens=resp.eval_count or 0,
            model=self.cfg.model,
            provider="ollama",
        )

    async def _ollama_stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]:
        import ollama
        stream = ollama.chat(
            model=self.cfg.model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            options={"temperature": self.cfg.temperature},
            stream=True,
        )
        for chunk in stream:
            if chunk.message.content:
                yield chunk.message.content

    def _openai_compat(self, messages: list[Message], **kwargs) -> LLMResponse:
        import openai
        if self.cfg.provider == "groq":
            _groq_limiter.acquire()
            client = openai.OpenAI(
                api_key=self.cfg.api_key,
                base_url="https://api.groq.com/openai/v1",
            )
        else:
            client = openai.OpenAI(api_key=self.cfg.api_key or None)

        resp = client.chat.completions.create(
            model=self.cfg.model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=self.cfg.temperature,
        )
        return LLMResponse(
            content=resp.choices[0].message.content or "",
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            model=self.cfg.model,
            provider=self.cfg.provider,
        )

    async def _openai_stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]:
        import openai
        if self.cfg.provider == "groq":
            await _groq_limiter.aacquire()
            client = openai.AsyncOpenAI(
                api_key=self.cfg.api_key,
                base_url="https://api.groq.com/openai/v1",
            )
        else:
            client = openai.AsyncOpenAI(api_key=self.cfg.api_key or None)

        stream = await client.chat.completions.create(
            model=self.cfg.model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=self.cfg.temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def _anthropic(self, messages: list[Message], **kwargs) -> LLMResponse:
        import anthropic
        client = anthropic.Anthropic(api_key=self.cfg.api_key or None)
        system = next((m.content for m in messages if m.role == "system"), "")
        chat_msgs = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        resp = client.messages.create(
            model=self.cfg.model,
            max_tokens=8096,
            system=system,
            messages=chat_msgs,
            temperature=self.cfg.temperature,
        )
        return LLMResponse(
            content=resp.content[0].text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=self.cfg.model,
            provider="anthropic",
        )

    async def _anthropic_stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self.cfg.api_key or None)
        system = next((m.content for m in messages if m.role == "system"), "")
        chat_msgs = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        async with client.messages.stream(
            model=self.cfg.model,
            max_tokens=8096,
            system=system,
            messages=chat_msgs,
            temperature=self.cfg.temperature,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    def _gemini(self, messages: list[Message], **kwargs) -> LLMResponse:
        import google.generativeai as genai
        genai.configure(api_key=self.cfg.api_key)
        model = genai.GenerativeModel(self.cfg.model)
        prompt = "\n".join(f"{m.role}: {m.content}" for m in messages)
        resp = model.generate_content(prompt)
        return LLMResponse(
            content=resp.text,
            model=self.cfg.model,
            provider="gemini",
        )


def get_llm(config: DevAgentConfig) -> LLMClient:
    """Return an LLMClient for the primary configured provider."""
    return LLMClient(config.llm)


def get_llm_for_task(config: DevAgentConfig, task: str) -> LLMClient:
    """Return an LLMClient routed by task type using RouterConfig.

    task: "planning" | "coding" | "reviewing" | "cheap"
    Falls back to primary llm config if router entry matches it.
    """
    from devagent.core.config import LLMConfig
    router_entry = getattr(config.router, task, None) or config.router.fallback
    routed_cfg = LLMConfig(
        provider=router_entry.get("provider", config.llm.provider),
        model=router_entry.get("model", config.llm.model),
        base_url=config.llm.base_url,
        temperature=config.llm.temperature,
        api_key=config.llm.api_key,
    )
    return LLMClient(routed_cfg)
