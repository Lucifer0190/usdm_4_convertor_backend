---
name: check
description: Run this repo's quality gate (git state, pytest, ruff check, guard.py) and report evidence, not claims.
allowed-tools: Bash(git status *) Bash(git diff *) Bash(python -m pytest *) Bash(ruff check *) Bash(python scripts/guard.py)
---

Live state:
- Status: !`git status --short`
- Diff summary: !`git diff HEAD --stat`

Run these, in order, and show the real output of each (do not summarize away failures):
1. `python -m pytest -q`
2. `ruff check src tests`
3. `python scripts/guard.py`

There is no typecheck and no build step in this repo; say so instead of inventing one. Then report:
- Pass/fail per step, with counts.
- Whether each failure comes from the current diff or was already there (compare failing file paths with
  the files in the diff).
- Anything you did not verify (for example the CORE gate, which needs `CDISC_LIBRARY_API_KEY`).
Do not edit files or fix issues here; just report.
