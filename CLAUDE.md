# USDM4-Assure

Converts clinical-trial protocol PDFs into conformant CDISC USDM 4.0 JSON. Accuracy comes first, and every
extracted value must be grounded in a verbatim quote. Code (never the model) resolves each quote to
page/character offset/bbox. Anything that can't be verified routes to human review; it is never forced
through. Do not weaken the Assurance layer (`assure/`) or the validation gates to make a domain pass.
`usdm4` is pinned to an exact version (see PINS.md). Build on the existing pipeline; don't work around it.

## Commands
Assumes an activated Python 3.12 env (conda `usdm4` or `.venv`). 3.13 breaks cdisc-rules-engine.
- Install: `python -m pip install -e ".[dev]"`
- Test (all / one file): `python -m pytest -q` / `python -m pytest tests/test_x.py -q`
- Lint: `ruff check src tests`
- Guardrails (CI runs them): `python scripts/guard.py`
- Typecheck: none configured. Build: none (Docker only: `docker compose build`).
- Smoke run: `python spikes/make_full_fixture.py`, then
  `python -m usdm4_assure.cli convert-full data/fixtures/protocol_full.pdf`
CI (`.github/workflows/ci.yml`) runs ruff check, guard.py, pytest, in that order.

## Conventions
- Work on `dev`, not `main`. Make small, logically scoped commits with `feat(scope):`, `fix(scope):`,
  `chore(scope):` prefixes, and push as you go.
- `.py` files stay under 400 lines (guard.py). `_ported_*.py` files are near-verbatim transplants from the
  reference extractor: exempt from the limit and not given tests. No hard-coded `C:\` or `/home/` paths in src.
- Google-style docstrings, typed public signatures, 100-char lines. Comments explain why, not what.
- Do NOT run `ruff format` on the tree: ~120 files aren't formatted, so it would rewrite them all.
- Throwaway scripts go in `spikes/_*.py` (gitignored), never in the tree.
- Model choice: use frontier LLMs by default. Use a small model (SLM) only where a measured eval shows it
  beats the LLM deterministically. Never pick a model to save cost. Roles are in `config/models.yaml`.

## Gotchas
- `tests/conftest.py` sets `USDM4_NO_LLM=1`. Tests never call a live model or write to the real `data/audit/`.
- `.env` holds API keys (`OPEN_ROUTER_KEY`, `ANTHROPIC_API_KEY`, `CDISC_LIBRARY_API_KEY`). Never read, print,
  or stage it. `data/` (except `data/labels/`) and `spikes/_work/` are gitignored; keep it that way.
- No real or sensitive protocol data in git. Use the synthetic fixtures (`spikes/make_*.py`).
- Serialize assembled studies with `json.dumps(obj, default=str)`. d4k result fields (`.passed`, `.count`)
  are properties, not methods.
- Logprobs must never be load-bearing anywhere in the pipeline (not all routed providers return them).
- `conda run ... python -c "<multi-line>"` fails: put scripts in a file.

## Keep docs in sync
- A prompt or model change may regress accuracy: re-run the suite and say what you saw.
- d4k/CORE result changes: update `docs/conformance.md`. Version-pin changes: update `PINS.md`.
- Notable changes: add a `CHANGELOG.md` entry under Unreleased.
- New domain extractor: ships with a synthetic-ground-truth fixture and a test that asserts its output.

## Hard rules
- Reuse existing patterns and utilities; don't add a dependency without asking.
- Never weaken or delete a test to make it pass.
- Never claim success without evidence: show the test/lint/guard output.
- Keep scope tight. Report out-of-scope findings separately instead of fixing them.

## Project memory
Shared, versioned state lives in `docs/ai/`: `STATE.md` (per-machine snapshot, gitignored), `PLANS.md`
(index of active work only), `DECISIONS.md`, `plans/`, `archive/`, `SPEC-template.md`. `PLAN.md` and
`DEVPLAN.md` at the repo root remain the long-term roadmap; they are not mirrored into `docs/ai/`.
There is no external tracker.

## Session protocol
- Start: STATE.md is injected by the SessionStart hook. Read the relevant lines of `docs/ai/PLANS.md` and the
  active plan file in `docs/ai/plans/`.
- Trivial change: inspect, implement, `/check`. Larger change: `/plan-task`, get approval, `/implement-plan`,
  `/check`, then the `reviewer` agent (or `/code-review`). If corrected twice on the same issue, stop and
  restart with a better prompt.
- End of a session or milestone: run `/sync-state`. It overwrites STATE.md, archives finished plans, records
  decisions, trims docs to their caps (CLAUDE.md 150 lines, STATE.md 60, PLANS.md 60, DECISIONS.md 40 entries),
  and shows the diff before anything is committed. `/ship` commits (only when asked).
- When compacting, always preserve the list of modified files, failing tests, and test commands.
