"""Claude adapter — primary model, tiered thinking (DESIGN.md §4).

Activates automatically when ANTHROPIC_API_KEY is set. Model ids are pinned in
one place so a model refresh is a config change, not a code change.
"""
from __future__ import annotations

import os

from usdm4_assure.llm.base import LLM, ModelTier, tier_for

# Pinned model ids per tier. Update here only.
TIER_MODEL: dict[ModelTier, str] = {
    ModelTier.HAIKU: "claude-haiku-4-5-20251001",
    ModelTier.SONNET: "claude-sonnet-5-5",
    ModelTier.OPUS: "claude-opus-5-5",
}

# Extended-thinking budget (tokens) per tier; 0 = off.
TIER_THINKING: dict[ModelTier, int] = {
    ModelTier.HAIKU: 0,
    ModelTier.SONNET: 0,
    ModelTier.OPUS: 4000,
}


class ClaudeLLM(LLM):
    name = "claude"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.available = bool(self.api_key)
        self._client = None

    def _client_lazy(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def complete(self, prompt: str, *, task: str = "extract_prose",
                 system: str | None = None, max_tokens: int = 1024) -> str:
        if not self.available:
            raise RuntimeError("ClaudeLLM called without ANTHROPIC_API_KEY")
        tier = tier_for(task)
        kwargs: dict = {
            "model": TIER_MODEL[tier],
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        budget = TIER_THINKING[tier]
        if budget:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
            kwargs["max_tokens"] = max(max_tokens, budget + 512)
        resp = self._client_lazy().messages.create(**kwargs)
        # Concatenate text blocks (skip thinking blocks).
        return "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        )
