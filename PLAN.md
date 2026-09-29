# USDM4 Converter: The One Plan

**This is the only plan.** Everything the core AI and the backend need to do lives here. Older plans are
in `docs/ai/archive/` for reference only and are not maintained. If work is not in this file, it is not planned.

Last updated: 2026-09-29 · Owner: project lead · Board: Trello "USDM_4" (card = one task ID below)

## 1. Goal

Upload a Pfizer-style protocol PDF, get back a conformant USDM 4.0 JSON that is **more than 89% accurate on
protocols the system has never seen**, with every value traceable to a quote in the PDF and anything doubtful
sent to a human instead of being guessed.

Two parts, one repo:

| Part | What it is | Where |
|---|---|---|
| **Core AI** ("brain") | Reads the PDF, extracts, checks, assembles USDM | `src/usdm4_assure/` |
| **Backend** | Thin HTTP service around the core: `POST /v1/convert` | `src/usdm4_api/` |

The backend never contains extraction logic. It only calls the `Converter` interface, so the brain can change
freely.

**Principles (decided):** the real API is **LLM-only** (no key, no conversion: it answers 503); rule-based readers
stay inside the pipeline only as an independent cross-check on the LLM. Backend repo:
`github.com/Lucifer0190/usdm_4_convertor_backend` (remote `origin`; the old repo is remote `legacy`).

## 2. What "89%" means (fixed, so it can be checked)

- Accuracy = matched items / (reference items + spurious delivered items). A wrong or invented item costs as
  much as a missing one. Defined in `src/usdm4_assure/eval/rubric.py`.
- Measured with `python spikes/run_benchmark.py` (add `--llm` for the LLM readers).
- **Train (may be tuned on):** C5091017, C4601003, C4891001, C4891002, C4891006.
- **Held-out (never tuned on, frozen):** C4891023, C4891024, C4891026.
- The headline number is the **held-out** score against the **audited gold**, not against the team's raw reference
  files (they contain known quirks, see the archived `ROAD_TO_89` §4).
- Open decision D2: 89% before human review, or after. Until decided, report both.

## 3. Where we are (measured 2026-09-29)

| Measure | Value |
|---|---|
| Deterministic accuracy, 8 studies, before the geometry SoA reader | 19.1% |
| Deterministic accuracy, 8 studies, after it | **36.2%** |
| Development study C5091017 | 77.8% |
| The other seven studies | 16–36% |
| LLM readers measured on the 8 studies | **not yet** |
| Backend API | works, LLM-only, 10 tests pass, live-tested on one protocol (38 s) |
| d4k rules on real studies | 0 of 23 pass (rules triage pending) |

The Schedule of Activities (SoA) is 60% of the score, so it decides whether we reach 89%.

## 4. Milestones (each ends in a number or a passing command)

| Milestone | Done when |
|---|---|
| **M0 Clean house** | One plan (this file, done), CI green, `dev` pushed to the backend repo |
| **M1 Trustworthy yardstick** | Audited gold exists for train and held-out sets; benchmark reports both |
| **M2 SoA general** | Held-out SoA items ≥ 85% |
| **M3 Whole study** | Held-out overall ≥ 75% pre-review, all categories extracted |
| **M4 Target** | Held-out overall > 89% (pre- or post-review per D2), risk-coverage curve published |
| **M5 Production-ready backend** | Async jobs, Linux/Docker verified, auth, logging, CORE gate optional |

## 5. Tasks

Model tags follow the working rule: **Haiku/Sonnet** for mechanical work, **Opus** for hard design.
Tasks are grouped by tier into checkpoints, so you switch model only at a checkpoint boundary. I will announce
each boundary ("switch to X, thinking Y"). Commit after each task; run `ruff check`, `python scripts/guard.py`
and `pytest` before each commit.

Track letters: **C** core AI, **B** backend, **Q** quality and evaluation, **H** housekeeping.

### CP-A · Sonnet / low · Housekeeping (M0)
| ID | Task | Done when |
|---|---|---|
| H-1 | Fix the 5 ruff errors listed in STATE.md | `ruff check src tests` clean |
| H-2 | Add `.gitattributes` (stop LF/CRLF churn) | no whole-file diffs on Windows |
| H-3 | Point remaining references (README, DESIGN.md, docs) at this plan or the archive | no link to a missing `DEVPLAN.md` |
| H-4 | Push `dev` to the backend repo (`origin` now points to `usdm_4_convertor_backend`; the old repo is remote `legacy`) | `dev` visible on GitHub |

### CP-B · Sonnet / medium · Backend hardening (M5)
| ID | Task | Done when |
|---|---|---|
| B-1 | Reject corrupt, encrypted and scanned PDFs with a clear 422 before the pipeline runs | test per case |
| B-2 | Async jobs: `POST /v1/jobs` returns an id, `GET /v1/jobs/{id}` returns status and result | a 5-minute conversion no longer holds one HTTP request |
| B-3 | `USDM4_RUN_CORE=1` runs the official CDISC CORE gate when `CDISC_LIBRARY_API_KEY` is set; result goes in the report, never blocks the response | report shows core status |
| B-4 | Return `run_id` and quality summary as response headers; structured request logs | one log line per request with run id |
| B-5 | Build and run the Docker image on Linux; document the deploy in `docs/api.md` | `docker compose --profile api up` converts the synthetic protocol |
| B-6 | Persistent volumes for `data/audit` and the LLM cache; document backup | run survives a container restart |

### CP-C · Sonnet / medium · Yardstick (M1)
| ID | Task | Done when |
|---|---|---|
| Q-1 | Freeze the train / held-out split in config; benchmark refuses to tune on held-out | split is code, not a note |
| Q-2 | Run invariants over all 204 protocol versions and record the baseline | table in `docs/scoreboard.md` |
| Q-3 | One benchmark run with `--llm` on the 8 studies (est. $5–15, D3 approved) | accuracy by category, LLM vs deterministic |
| Q-4 | **Audited gold**: a clinical data manager corrects our output in the review UI for train and held-out studies (about a day per study; human task, D1) | gold labels committed under `data/labels/` |

### CP-D · Opus / high · SoA generality and AI reader (M2)
| ID | Task | Done when |
|---|---|---|
| C-1 | SoA layouts still failing: cycle-based headers, duplicate visit names, empty visit columns, tables without ruling lines, reduced or amended schedules, several tables, footnote conditions | ≥ 85% SoA on train; then measured on held-out |
| C-2 | **AI SoA reader**: vision model (Gemini 3.1 Pro, cross-checked by Sonnet 5.5) reads the table page images; the geometry reader is the independent check; disagreements go to review | disagreement rate reported |
| C-3 | **Bake-off** on the same pages: geometry vs vision LLM vs Granite-Docling vs Docling (D3 approved) | one table, one winner per layout type |
| C-4 | Sub-study schedules become separate timelines instead of one merged table | test on a two-schedule protocol |

### CP-E · Sonnet / medium · The rest of the study (M3)
| ID | Task | Done when |
|---|---|---|
| C-5 | Objectives and endpoints reader for two-column, phase-split and per-population tables | ≥ 90% held-out on those categories |
| C-6 | Identifiers (IND, EU CT, NCT, PIP, compound), vendors and organisations, narrative sections | measured recall per category |
| C-7 | LLM readers for arms, interventions, sponsor, version, estimand attributes (already built): measure and tune on train only | scored with `--llm` |
| C-8 | Remove placeholder fabrication in `assemble/sanitize.py`; missing data stays missing and is flagged | no invented values in output |
| C-9 | OCR fallback for scanned pages | a scanned test PDF converts or is refused cleanly |

### CP-F · Opus / high · Assurance on real data (M4)
| ID | Task | Done when |
|---|---|---|
| C-10 | Calibrate confidence on gold; conformal threshold decides auto-accept vs review | risk-coverage curve on held-out |
| C-11 | Triage d4k rules failing on real studies (DDF00213, DDF00247 and others) | each failure classed as our bug, rule bug or data issue |
| C-12 | Real CORE run with the CDISC key; compare with d4k | `docs/conformance.md` updated |
| C-13 | Pin `cdisc-rules-engine` exactly in `PINS.md` | pin recorded |

Order: **CP-A → CP-C (Q-1, Q-2, Q-4 start now, it is the long pole) → CP-D → CP-E → CP-F**, with CP-B slotted
in whenever the backend is needed by the frontend team.

## 6. Decisions still needed from the project lead

| ID | Decision | Blocks |
|---|---|---|
| D1 | Who audits the gold (clinical data manager)? | Q-4, M1 and everything measured after it |
| D2 | Is 89% before or after human review? | M4 wording |
| D3 | **Decided:** the real API is LLM-only; LLM benchmark runs are approved. **Open:** a monthly spend cap (proposal: alert at $50, stop at $100) | Q-3, C-2, C-3 cost control |
| D4 | Approve the train and held-out split in section 2 | Q-1 |
| D5 | **Decided:** backend repo is `github.com/Lucifer0190/usdm_4_convertor_backend` | - |

## 7. Rules that keep this the only plan

1. New work is added here as a task ID with a model tag and a "done when". Not in a new file.
2. `docs/ai/PLANS.md` is only the index of what is Now, Next and Later, using these IDs.
3. Each task ID gets one Trello card. The card holds the assignee, label and due date; this file holds the scope.
4. A finished task is ticked in the changelog, not deleted here until the milestone closes.
5. Research or design write-ups are allowed, but they go in `docs/` and are linked from a task. They are not plans.
6. Never weaken the grounding rule or the validation gates to lift a score.
