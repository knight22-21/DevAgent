"""LLM provider factory, rate limiting, fallback logic."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from specsync.core.config import SpecSyncConfig


class TokenBucket:
    """A simple token-bucket rate limiter."""
    def __init__(self, tokens_per_minute: int):
        self.capacity = tokens_per_minute
        self.tokens = float(tokens_per_minute)
        self.fill_rate = tokens_per_minute / 60.0
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    def _update_tokens(self) -> None:
        now = time.monotonic()
        delta = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + delta * self.fill_rate)
        self.last_update = now

    def acquire(self) -> None:
        """Synchronously acquire a token, sleeping if necessary."""
        while True:
            self._update_tokens()
            if self.tokens >= 1:
                self.tokens -= 1
                return
            time.sleep(1 / self.fill_rate)

    async def aacquire(self) -> None:
        """Asynchronously acquire a token, sleeping if necessary."""
        while True:
            async with self._lock:
                self._update_tokens()
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
            await asyncio.sleep(1 / self.fill_rate)


# Global rate limiter for Groq (30 RPM free tier)
_groq_limiter = TokenBucket(30)


def _get_base_llm(provider: str, model: str, base_url: str, api_key: str, temperature: float) -> BaseChatModel:
    """Instantiate a LangChain chat model based on provider."""
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model,
            base_url=base_url,
            temperature=temperature,
        )
    elif provider == "groq":
        from langchain_groq import ChatGroq
        
        class RateLimitedChatGroq(ChatGroq):
            def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> Any:
                _groq_limiter.acquire()
                return super()._generate(messages, stop, run_manager, **kwargs)

            async def _agenerate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> Any:
                await _groq_limiter.aacquire()
                return await super()._agenerate(messages, stop, run_manager, **kwargs)

        return RateLimitedChatGroq(
            model=model,
            api_key=api_key,
            temperature=temperature,
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            api_key=api_key,
            temperature=temperature,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=temperature,
        )
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model,
            api_key=api_key,
            temperature=temperature,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def get_llm(config: SpecSyncConfig) -> BaseChatModel:
    """Return the primary configured LLM."""
    return _get_base_llm(
        provider=config.llm.provider,
        model=config.llm.model,
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        temperature=config.llm.temperature,
    )


def get_llm_with_fallback(config: SpecSyncConfig) -> BaseChatModel:
    """Return the primary LLM wrapped with the fallback LLM (if configured)."""
    primary = get_llm(config)
    
    if config.llm.fallback and config.llm.fallback.provider:
        fallback = _get_base_llm(
            provider=config.llm.fallback.provider,
            model=config.llm.fallback.model,
            base_url=config.llm.base_url,  # base_url usually only applies to ollama
            api_key=config.llm.fallback.api_key,
            temperature=config.llm.temperature,
        )
        return primary.with_fallbacks([fallback])
    
    return primary
