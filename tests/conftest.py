"""Pytest configuration.

Forces the deterministic (no-LLM) path so the suite is fast, free, offline, and
reproducible even when an OpenRouter/Anthropic key is present in the environment.
The Assurance ensemble's deterministic members carry the run; the LLM member is
exercised manually via the CLI, not in unit tests.
"""
import os

import pytest

os.environ["USDM4_NO_LLM"] = "1"


@pytest.fixture(autouse=True)
def _isolated_audit_dir(tmp_path, monkeypatch):
    """Redirect the Part 11 audit store to a temp dir so run_full() in tests
    never writes into the real data/audit/ (AuditStore.__init__ picks this up
    via USDM4_AUDIT_DIR whenever a test doesn't pass its own path)."""
    monkeypatch.setenv("USDM4_AUDIT_DIR", str(tmp_path / "audit"))
