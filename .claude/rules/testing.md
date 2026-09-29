---
paths:
  - "tests/**"
  - "spikes/make_*.py"
---

# Testing rules

- Every extractor is scored against synthetic ground truth: a new domain ships with a fixture
  (`spikes/make_*.py`) and a test that asserts its output, not just that it runs.
- Tests never call a live model. `tests/conftest.py` sets `USDM4_NO_LLM=1` so the router uses the stub;
  keep it that way, and never require an API key to pass the suite.
- The Part 11 audit store is redirected to a temp dir by conftest. Never write to the real `data/audit/`.
- Tests that need the gitignored usdm_data corpus must skip when it is absent, not fail.
- Code in `_ported_*.py` files is used as-is and gets no tests; test only code we author.
- Never weaken an assertion, loosen a threshold, or add a skip to make a test pass. If a test is wrong,
  say so and explain before changing it.
- Synthetic fixtures only. No real or sensitive protocol data in the repo.
