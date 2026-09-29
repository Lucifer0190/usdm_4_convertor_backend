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
