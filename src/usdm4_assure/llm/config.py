"""LLM configuration — loads the local .env and resolves the OpenRouter key.

Kept in one place so the key name is defined once. The project standardizes on
**OpenRouter** (one key, many models) with Claude as the default choice.
"""
from __future__ import annotations

import os

try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except Exception:  # noqa: BLE001, S110 — dotenv optional; env vars may be set directly
    pass

# The .env in this project uses OPEN_ROUTER_KEY; accept the common alias too.
_KEY_NAMES = ("OPEN_ROUTER_KEY", "OPENROUTER_API_KEY")

# Default SLM. No clinically fine-tuned model is hosted on OpenRouter, so we use a
# small, cheap, medically-competent general model. Llama 3.1 8B is the design's cited
# choice (a distilled 8B beat its 70B teacher on eligibility-criteria extraction) and
# costs ~$0.05/$0.08 per M tokens. Override with OPENROUTER_SLM_MODEL.
DEFAULT_SLM_MODEL = "meta-llama/llama-3.1-8b-instruct"


def openrouter_key() -> str | None:
    """Return the OpenRouter API key from the environment, or ``None``."""
    for name in _KEY_NAMES:
        if val := os.environ.get(name):
            return val
    return None


def slm_model() -> str:
    """Return the configured SLM model slug (env override or default)."""
    return os.environ.get("OPENROUTER_SLM_MODEL", DEFAULT_SLM_MODEL)


_DEFAULT_ROLE_MODELS: dict[str, str] = {
    "extract": "anthropic/claude-sonnet-5.5",
    "extract_alt": "openai/gpt-6-sol",
    "verify": "google/gemini-3.1-pro-preview",
    "vision": "google/gemini-3.1-pro-preview",
    "vision_alt": "anthropic/claude-sonnet-5.5",
    "hard_reasoning": "anthropic/claude-opus-5.5",
    "route": "anthropic/claude-sonnet-5.5",
}


def model_for(role: str) -> str:
    """Return the OpenRouter model slug for a role (env override or default).

    Args:
        role: Role name (e.g., 'extract', 'verify', 'hard_reasoning').

    Returns:
        An OpenRouter model slug, overridable via ``USDM4_MODEL_<ROLE>``
        (e.g., ``USDM4_MODEL_EXTRACT`` for the 'extract' role).

    Raises:
        KeyError: If the role is not recognized.
    """
    if role not in _DEFAULT_ROLE_MODELS:
        raise KeyError(f"Unknown role: {role}")
    return os.environ.get(f"USDM4_MODEL_{role.upper()}", _DEFAULT_ROLE_MODELS[role])
