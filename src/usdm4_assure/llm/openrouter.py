"""OpenRouter adapter — the project's default LLM gateway.

OpenRouter exposes an OpenAI-compatible endpoint that fronts many providers behind
one key, which lets the Assurance ensemble mix model *families* for error
independence. We default to Claude (per project direction) but any OpenRouter model
slug can be selected per member.

Model ids are OpenRouter slugs (verified against the live catalog) and can be
overridden via ``OPENROUTER_MODEL_{HAIKU,SONNET,OPUS}`` environment variables.

Every completion is content-addressed and cached (:mod:`usdm4_assure.llm.cache`):
at ``temperature=0`` a call is a pure function of ``(model, messages, max_tokens)``,
so re-running the eval harness or re-processing an unchanged protocol costs nothing
after the first pass, and the cache key doubles as the audit trail's stable
``prompt_hash``. Transient failures (429 rate limit, 5xx) are retried with
exponential backoff before giving up.
"""
from __future__ import annotations

import os
import time

import requests

from usdm4_assure.llm.base import LLM, ModelTier, tier_for
from usdm4_assure.llm.cache import LLMCache, cache_key, default_cache
from usdm4_assure.llm.config import model_for, openrouter_key

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Retryable HTTP statuses: 429 (rate limit) and 5xx (transient provider error).
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 4
_BACKOFF_BASE_SECONDS = 1.0
# An empty completion means the model spent its whole budget before answering (a
# reasoning model's thinking counts against ``max_tokens``). Retry once with a
# larger budget; the cap keeps a runaway prompt from asking for an absurd one.
_EMPTY_RETRY_FACTOR = 2
_MAX_RETRY_TOKENS = 16000

# Default Claude tier -> OpenRouter slug (current catalog).
_DEFAULT_TIER_MODEL: dict[ModelTier, str] = {
    ModelTier.HAIKU: "anthropic/claude-haiku-4.5",
    ModelTier.SONNET: "anthropic/claude-sonnet-5.5",
    ModelTier.OPUS: "anthropic/claude-opus-5.5",
}


def _tier_model(tier: ModelTier) -> str:
    return os.environ.get(f"OPENROUTER_MODEL_{tier.name}", _DEFAULT_TIER_MODEL[tier])


class OpenRouterLLM(LLM):
    """An LLM member served through OpenRouter.

    Args:
        model: Explicit OpenRouter slug to force one model for every task. When
            ``None`` and ``role`` is also ``None``, the model is chosen per task
            from the Claude tier map (legacy behavior).
        role: Role name (e.g., 'extract', 'verify') for role-based model routing.
            Ignored if ``model`` is set (explicit model takes precedence).
        name: Ensemble-member tag recorded in provenance (default ``"claude"``
            since Claude is the default family).
        timeout: Per-request timeout in seconds.
        cache: Cache instance to use. Defaults to the process-wide
            :func:`usdm4_assure.llm.cache.default_cache`. Pass ``False`` to
            disable caching for this instance.
    """

    def __init__(self, model: str | None = None, role: str | None = None,
                 name: str = "claude", timeout: float = 60.0,
                 cache: LLMCache | bool | None = None) -> None:
        self.api_key = openrouter_key()
        self.available = bool(self.api_key)
        self.model = model
        self.role = role
        self.name = name
        self.timeout = timeout
        self._cache = None if cache is False else (cache or default_cache())

    def complete(self, prompt: str, *, task: str = "extract_prose",
                 system: str | None = None, max_tokens: int = 1024) -> str:
        """Call the model and return its text.

        Args:
            prompt: The user message.
            task: Logical task name; selects the Claude tier when ``model`` is
                unset (see ``llm.base.TASK_TIER``).
            system: Optional system prompt.
            max_tokens: Response token cap.

        Returns:
            The assistant message text (empty string if the response is empty).

        Raises:
            RuntimeError: If called without a key, or every retry attempt fails.
        """
        if not self.available:
            raise RuntimeError("OpenRouterLLM called without an OpenRouter key")
        if self.model:
            model = self.model
        elif self.role:
            model = model_for(self.role)
        else:
            model = _tier_model(tier_for(task))
        messages = ([{"role": "system", "content": system}] if system else [])
        messages.append({"role": "user", "content": prompt})

        key = cache_key(model, messages, max_tokens)
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

        text = self._call_checked(model, messages, max_tokens)

        if self._cache is not None:
            self._cache.put(key, model=model, prompt_hash=key, response=text)
        return text

    def complete_vision(self, image_b64: str, prompt: str, *, system: str | None = None,
                        max_tokens: int = 512, mime: str = "image/png") -> str:
        """Call a vision-capable model with one image and a text prompt.

        Not part of the ``LLM`` protocol (duck-typed): callers check
        ``getattr(llm, "complete_vision", None)`` rather than requiring every
        member to support it, since most extraction is text-only. Selects a
        model the same way :meth:`complete` does, defaulting to the
        ``"vision"`` role when neither ``model`` nor ``role`` is set.

        Args:
            image_b64: The image, base64-encoded (no data-URI prefix).
            prompt: The text prompt accompanying the image.
            system: Optional system prompt.
            max_tokens: Response token cap.
            mime: Image MIME type.

        Returns:
            The assistant message text (empty string if the response is empty).
        """
        if not self.available:
            raise RuntimeError("OpenRouterLLM called without an OpenRouter key")
        model = self.model or model_for(self.role or "vision")
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
        ]
        messages = ([{"role": "system", "content": system}] if system else [])
        messages.append({"role": "user", "content": content})

        key = cache_key(model, messages, max_tokens)
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

        text = self._call_checked(model, messages, max_tokens)

        if self._cache is not None:
            self._cache.put(key, model=model, prompt_hash=key, response=text)
        return text

    def _call_checked(self, model: str, messages: list[dict], max_tokens: int) -> str:
        """One completion that must contain text.

        An empty answer is retried once with a larger token budget. If it is
        still empty the call raises: an empty string looks like "the model found
        nothing", which is exactly how the failure used to go unnoticed.
        """
        text = self._call_with_retry(model, messages, max_tokens)
        if text.strip():
            return text
        bigger = min(max_tokens * _EMPTY_RETRY_FACTOR, _MAX_RETRY_TOKENS)
        text = self._call_with_retry(model, messages, bigger)
        if not text.strip():
            raise RuntimeError(
                f"{model} returned an empty completion twice "
                f"(max_tokens {max_tokens} then {bigger})")
        return text

    def _call_with_retry(self, model: str, messages: list[dict], max_tokens: int) -> str:
        last_error: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = requests.post(
                    _ENDPOINT,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        # Optional attribution headers OpenRouter recommends.
                        "HTTP-Referer": "https://hexaware.com",
                        "X-Title": "USDM4-Assure",
                    },
                    json={"model": model, "messages": messages, "max_tokens": max_tokens},
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                last_error = e
            else:
                if resp.status_code == 200:
                    choices = resp.json().get("choices", [])
                    if not choices:
                        return ""
                    return choices[0].get("message", {}).get("content", "") or ""
                if resp.status_code not in _RETRY_STATUSES:
                    raise RuntimeError(f"OpenRouter {resp.status_code}: {resp.text[:200]}")
                last_error = RuntimeError(f"OpenRouter {resp.status_code}: {resp.text[:200]}")

            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_BACKOFF_BASE_SECONDS * (2 ** attempt))

        raise RuntimeError(
            f"OpenRouter call failed after {_MAX_ATTEMPTS} attempts: {last_error}"
        )
