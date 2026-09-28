"""Model router — returns the active LLM member, or a stub when no key is present.

Resolution order (Claude-first, per project direction):
    1. OpenRouter (the standard gateway; one key, many models) — default Claude.
    2. Direct Anthropic SDK, if only ``ANTHROPIC_API_KEY`` is set.
    3. ``StubLLM`` — no key: the deterministic ensemble members carry the run.

The pipeline calls :func:`get_llm` once; extractors and the verifier check the
returned object's ``available`` flag and include it as an ensemble member if so.

Set ``USDM4_REQUIRE_LLM=1`` to make a missing key a hard failure instead of a
silent fall-through to the stub — useful for a Phase-0-style measurement run
where a quietly-deterministic-only pass would produce a misleadingly low
grounded-field count rather than an honest configuration error.
"""
from __future__ import annotations

import os

from usdm4_assure.llm.base import LLM
from usdm4_assure.llm.claude import ClaudeLLM
from usdm4_assure.llm.config import openrouter_key, slm_model
from usdm4_assure.llm.openrouter import OpenRouterLLM


class StubLLM(LLM):
    """No-op LLM used when no API key is configured.

    It is ``available = False``, so extractors simply skip the LLM ensemble member
    and the deterministic paths carry the run. Calling it is a programming error.
    """
    name = "stub"
    available = False

    def complete(self, prompt: str, *, task: str = "extract_prose",
                 system: str | None = None, max_tokens: int = 1024) -> str:
        raise RuntimeError(
            "StubLLM.complete called — guard with `if llm.available` before use."
        )


def get_llm(model: str | None = None) -> LLM:
    """Return the active LLM member.

    Args:
        model: Optional explicit OpenRouter slug to pin one model (e.g. a second
            family for ensemble diversity). Ignored when no OpenRouter key is set.

    Returns:
        An ``OpenRouterLLM`` (preferred), a direct ``ClaudeLLM``, or a ``StubLLM``.
    """
    # Deterministic/offline escape hatch — set by the test suite so runs never make
    # live, paid, non-deterministic LLM calls (the deterministic ensemble carries it).
    if os.environ.get("USDM4_NO_LLM"):
        return StubLLM()
    if openrouter_key():
        return OpenRouterLLM(model=model)
    claude = ClaudeLLM()
    if claude.available:
        return claude
    if os.environ.get("USDM4_REQUIRE_LLM"):
        raise RuntimeError(
            "USDM4_REQUIRE_LLM is set but no LLM key is configured "
            "(OPEN_ROUTER_KEY/OPENROUTER_API_KEY or ANTHROPIC_API_KEY)."
        )
    return StubLLM()


def get_role_llm(role: str) -> LLM:
    """The OpenRouter member for one ``config/models.yaml`` role, or a ``StubLLM``.

    Used where a task names its role explicitly (e.g. estimands: the
    ``hard_reasoning`` role as primary, ``extract_alt`` as the second,
    different-family member). Honors ``USDM4_NO_LLM``; no OpenRouter key means
    a stub, so the deterministic members carry the run.
    """
    if os.environ.get("USDM4_NO_LLM") or not openrouter_key():
        return StubLLM()
    return OpenRouterLLM(role=role, name=role)


def get_slm(model: str | None = None) -> LLM:
    """Return the small-model (SLM) member for narrow tasks and ensemble diversity.

    A different, cheaper family than Claude (default Llama 3.1 8B via OpenRouter), so
    Claude+SLM agreement is a genuine cross-family signal. Honors ``USDM4_NO_LLM``
    and returns a ``StubLLM`` when no OpenRouter key is present.

    Args:
        model: Optional slug override; defaults to :func:`config.slm_model`.

    Returns:
        An ``OpenRouterLLM`` tagged ``"slm"`` or a ``StubLLM``.
    """
    if os.environ.get("USDM4_NO_LLM") or not openrouter_key():
        return StubLLM()
    return OpenRouterLLM(model=model or slm_model(), name="slm")
