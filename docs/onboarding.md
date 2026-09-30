# Onboarding: taking this project forward

For an engineer (or Claude Code) picking up the project cold. About an hour to read, then you can
run the benchmark and pick a task. This page is a reading order and a set of gotchas, not a plan:
**the only plan is [`PLAN.md`](../PLAN.md)**.

## What it is

A protocol PDF goes in; a conformant CDISC USDM 4.0 JSON comes out. Two parts, one repo:

| Part | Where | Job |
|---|---|---|
| Core AI ("brain") | `src/usdm4_assure/` | Reads the PDF, extracts, checks, assembles USDM |
| Backend | `src/usdm4_api/` | HTTP wrapper: `POST /v1/convert`, `POST /v1/jobs` |

Rules the whole design rests on: every value is grounded in a verbatim quote (code, never the model,
resolves it to page and position); anything unverifiable goes to human review instead of being
guessed; the LLM proposes and code disposes. Never trade these for a higher score.

## Read in this order

1. [`PLAN.md`](../PLAN.md): goal, the definition of "89%", status, every task and what blocks it.
2. [`docs/scoreboard.md`](scoreboard.md): every measurement so far, including what did *not* work.
3. [`docs/conformance.md`](conformance.md): every d4k rule that fails, and why (ours, the rule's, or the data's).
4. [`DESIGN.md`](../DESIGN.md) and [`docs/pipeline.md`](pipeline.md): the layers and data contracts.
5. [`docs/api.md`](api.md): running and deploying the service.
6. [`CLAUDE.md`](../CLAUDE.md): commands and conventions (also what Claude Code loads each session).

## Set up and check it works

```bash
python -m pip install -e ".[dev,api]"          # Python 3.12; 3.13 breaks cdisc-rules-engine
cp .env.example .env                            # add OPEN_ROUTER_KEY (and CDISC_LIBRARY_API_KEY for CORE)
python -m pytest -q                             # ~640 tests, ~4 min, never calls a live model
ruff check src tests
python spikes/make_full_fixture.py && python -m usdm4_assure.cli convert-full data/fixtures/protocol_full.pdf
```

## Measure before and after every change

```bash
python spikes/run_benchmark.py --ddf-root "<Digital Data Flow (Downstream)>" --out <dir>            # train set, deterministic, free
python spikes/run_benchmark.py ... --llm                                                             # with the LLM readers (costs money; responses are cached)
python spikes/run_soa_bakeoff.py ...                                                                 # SoA readers head to head
python spikes/run_invariants.py ... --all-versions                                                   # label-free checks over all 204 protocols
```

The protocol packet is Pfizer data and lives **outside git** (ask the project lead for it). Studies are
split **train** (develop and tune on these) and **held-out** (`eval/split.py`): held-out is scored rarely,
needs `--confirm-heldout`, and each run is logged. Never tune on it, or the number means nothing.

## Hard-won facts (each cost real time)

- **usdm4's `name` is a slug; the text is in `label`.** `StudyArm.name = label.upper().replace(" ", "-")`.
  Compare and display `label` (`eval/rubric._display`). Scoring `name` hid a real bug for weeks.
- **The reference is not gold.** Several categories (vendors, endpoints, some SoA) are limited by the
  team's reference files paraphrasing or enriching the protocol, not by extraction. Only the audited
  gold set (task Q-4) can settle them. Check a miss against the PDF before "fixing" it.
- **Empty is better than invented.** `assemble/sanitize.py` leaves gaps empty and reports them. The one
  exception is `Organization.name` / `Study.name` (usdm4 requires non-empty): `"[not extracted]"`.
- **Every fix is checked on the development study *and* the others.** The readers were first built on one
  study (C5091017, ~77%) and the rest scored 16-36%. That gap is the over-fitting the split exists to catch.
- **d4k and CORE are different result objects**; see `validate/gate.py`. CORE needs `CDISC_LIBRARY_API_KEY`
  and downloads its rules on first run; the free key does not include controlled-terminology packages.
- **Windows:** files are CRLF; keep scripts in files (multi-line `python -c` breaks); PDFs use the PUA
  bullet U+F0B7.
- `scripts/guard.py` (400-line limit) currently fails on `pipeline.py` and `extract/soa/geometry.py`:
  a known, deferred split (see PLAN.md H-1).

## What is left (details in PLAN.md)

Blocked on people: **Q-4** audited gold set (decision D1), which unlocks **C-10** calibration; **B-5** run
the Docker image once on a machine with Docker. Open engineering: **C-1** remaining SoA layouts, **C-4**
sub-study schedules as separate timelines, narrative sections. Train accuracy is ~43% with the LLM readers
against a >89% goal; the held-out studies have not been scored yet.
