# Scoreboard

Generated 2026-09-29T06:37:53+00:00. `usdm4` and rule-set pins: see `PINS.md`.

23/23 studies assembled without error (0 pipeline error(s)).

| Metric | Value |
|---|---|
| Structural pass rate | 23/23 |
| d4k pass rate | 0/23 |
| CORE status (per study) | skipped: 23 |
| Auto-accept coverage | 8.9% |
| Review burden | 59.0% |
| Assembler reliance ratio (mean) | 99.4% |
| Realized error (labelled studies) | 14.3% (n=62 labels, 4 studies) |

> **Small-sample caveat.** DESIGN.md §5 anticipates ~1,200 field-level labels from ~20 protocols; only 62 labels across 4 studies exist today (task 4.1). Realized error above describes that small set, not a general accuracy claim. There is no certified conformal auto-accept threshold yet (task 4.3) — too few calibration points — so `auto_accept` above still comes from the pre-Phase-4 hand-set confidence formula, not a statistically-bounded one.

## d4k rule failures across the corpus

| Rule | Studies failing |
|---|---|
| `DDF00101` | 23 |
| `DDF00140` | 23 |
| `DDF00200` | 23 |
| `DDF00031` | 22 |
| `DDF00075` | 22 |
| `DDF00097` | 22 |
| `DDF00213` | 15 |
| `DDF00247` | 13 |
| `DDF00041` | 8 |
| `DDF00084` | 6 |
| `DDF00153` | 6 |
| `DDF00012` | 1 |
| `DDF00040` | 1 |

## Repair loop: rules the bounded loop could not resolve

| Rule | Studies |
|---|---|
| `DDF00101` | 23 |
| `DDF00140` | 23 |
| `DDF00200` | 23 |
| `DDF00031` | 22 |
| `DDF00075` | 22 |
| `DDF00097` | 22 |
| `DDF00213` | 15 |
| `DDF00247` | 13 |
| `DDF00041` | 8 |
| `DDF00084` | 6 |
| `DDF00153` | 6 |
| `DDF00012` | 1 |
| `DDF00040` | 1 |

## Structural invariants over all 204 protocol versions (2026-09-29, no labels)

Baseline for generalisation (PLAN.md task Q-2). No crashes. Full table and the failing-file list are in
`spikes/reports/invariants_all_versions.md`; reproduce with `spikes/run_invariants.py --all-versions`.

| Area | Invariant | Holds |
|---|---|---:|
| Sections | every slot found (7 of 7) | 100% |
| SoA | grid found | 99% |
| SoA | marks in range / activity names label-sized | 99% / 98% |
| SoA | most activities are scheduled | 95% |
| SoA | every visit has a mark | **62%** |
| SoA | visit names unique enough | **61%** |
| Eligibility | inclusion / exclusion lists present | 91% / 93% |
| Eligibility | items are criterion-sized | 87% |
| Objectives | table found | 99% |
| Objectives | every row has an endpoint | 88% |

The two weak spots are both SoA: duplicate visit names and visit columns with no mark. They are the
large oncology schedules with cycle-based headers (C4891xxx, C2321xxx, C1071xxx), so they are the first
target of PLAN.md task C-1.

## LLM readers vs deterministic, train studies (2026-09-29, PLAN.md task Q-3)

Five train studies, 976 reference items, scored with `eval/rubric.py` against the team's reference USDMs
(not yet audited gold). Full report: `spikes/reports/benchmark_train_llm.md`. Held-out studies were not run.

| | Accuracy | Recall |
|---|---:|---:|
| Deterministic only | 40.3% | 53.9% |
| LLM readers on | **40.7%** | **58.0%** |

| Category | Deterministic recall | LLM recall |
|---|---:|---:|
| scalars (title, sponsor, phase...) | 50% | **94%** |
| arms | 44% | **89%** |
| interventions | 33% | **58%** |
| endpoints | 37% | **53%** |
| estimands | 30% | **50%** |
| criteria, objectives | 81% | 81–83% |
| activities, marks, visits, epochs | 38–67% | same (the LLM does not read the SoA) |
| identifiers, vendors | 17%, 0% | same (no reader yet) |

The LLM lifts the fields it reads, but the overall score barely moves for two reasons:
1. **The SoA is 60% of the score and no LLM reads it yet.** That is task C-2.
2. **It adds wrong or extra items** (416 spurious items across the five studies), and those count against accuracy.

Per study: C5091017 75.2%, C4601003 38.9%, C4891001 29.0%, C4891002 21.3%, C4891006 36.3%.

## SoA reader fixes (C-1), 2026-09-29

The rubric now keeps numeric tokens ("Day 1" is not "Day 15"), which lowered the earlier train baselines
to 39.5% deterministic / 39.9% with LLM readers. After the SoA header, continuation, notes-column and
PK-table fixes (deterministic, train set): **39.9%** overall, visit recall **37% -> 63%**, wrong epochs 28 -> 13.
The remaining SoA gap on C4891002 / C4891006 is mostly reference quirks (the reference holds the
superseded schedule from the amendment appendix), so it is left for the audited gold (Q-4).

Invariants over all 204 protocol versions, before -> after:

| SoA invariant | Before | After |
|---|---:|---:|
| every visit has a mark | 62% | **89%** |
| visit names unique enough | 61% | **97%** |
| visit names are real | 96% | 98% |
| every visit has an epoch | 98% | 84% |

The epoch drop is 27 vaccine-style protocols whose table has a visit-number row and no period band: the
"epochs" were visit numbers before. Their epochs must come from outside the table (open item under C-1).
