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
