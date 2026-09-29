---
name: implement-plan
description: Implement an approved plan from docs/ai/plans in small verified slices, updating docs/ai/STATE.md after each slice.
argument-hint: "[plan id or file]"
---

Implement: $ARGUMENTS

1. Read the approved plan file in `docs/ai/plans/` (ask which one if unclear). If none is approved, stop and
   suggest `/plan-task`.
2. Work one slice at a time, following the plan's checkpoint order. Announce any model/thinking switch the
   plan calls for and stop until the user has switched.
3. After each slice run the focused checks and show the output:
   - `python -m pytest tests/<relevant>.py -q`
   - `ruff check <changed files>`
   - `python scripts/guard.py`
4. Overwrite `docs/ai/STATE.md` with the current state after each slice (cap 60 lines).
5. Stay in scope. Don't weaken tests. List out-of-scope findings separately at the end.
6. Don't commit unless the user asks; `/ship` does that.
