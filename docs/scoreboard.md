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

## SoA bake-off: geometry vs vision (C-2 / C-3), 2026-09-30

Same schedule pages, SoA categories only (`spikes/run_soa_bakeoff.py`, `eval.rubric.score_grid`).
Vision = Gemini 3.1 Pro page images + text layer, JSON per page, stitched and normalised by code.

| Study | Geometry | Vision |
|---|---:|---:|
| C5091017 | **76.8%** | 67.4% |
| C4601003 | **80.3%** | 73.3% |
| C4891001 | **26.7%** | 18.4% (only 12 of 19 pages sent) |
| C4891002 | 9.0% | 10.1% |
| C4891006 | 19.5% | 19.5% |
| **Pooled** | **40.3%** | 36.2% |

Vision improved from 48.6% to 67.4% on C5091017 over three iterations (token budget for reasoning,
previous page's columns passed to continuation pages, shared name normalisation). Labels are 85–100%
grounded in the page text.

Does agreement predict a correct mark? On C5091017, the one study whose reference matches the current
schedule: marks both readers give 76% correct, geometry-only 81%, vision-only 15%. So vision's extra
marks are mostly wrong, and disagreement does not flag geometry's errors well.

**Decision:** geometry is the delivered SoA on ruled tables; vision is not merged (a union adds false
marks). Vision is the fallback when no ruled table is found (tables without rules, scans, unfamiliar
layouts), with every mark routed to review. Docling / Granite-Docling were not run: on ruled Pfizer
tables the geometry reader already reads the exact grid, so they would compete only for the fallback.

## Identifiers reader (C-6), 2026-09-30

Deterministic title-page label parser (`extract/identifiers.py`): NCT, EU CT / EudraCT, US
IND, PIP and compound codes, alongside C1 metadata's protocol number. Train set, deterministic:

| | Before | After |
|---|---:|---:|
| identifiers recall | 17% (4/23) | **78% (18/23)** |
| overall accuracy | 39.9% | 40.9% |
| overall recall | 56.4% | 57.8% |

Per study: C5091017 5/6, C4891001 4/4, C4891002 4/4, C4891006 4/5, C4601003 1/4. The one
weak study's reference labels its own values ("EudraCT Number: 2021-005427-20" instead of
the bare number) inconsistently with the other four references (bare "2021-005427-20"
style) — the identifier rubric matches at an exact 1.0 threshold, so this is a reference
formatting inconsistency, not an extraction gap; the audited gold set (Q-4) should settle it.

## Vendors: a groundability finding, not yet an extractor (C-6)

Checked whether the reference's "vendors" (organisations other than the sponsor) are
literally present in the protocol text they are supposedly extracted from, across the 3
studies with the most vendor items (`spikes/_vendor_probe.py`). Result is split:

- **Generic role-based names never appear**: "Central Laboratory", "Central Imaging
  Vendor", "Central ECG Vendor", "IRT/RTSM System", "eCOA/ePRO Vendor" — 0 occurrences in
  C4891006's full text (all pages, exact and case-insensitive). These look like standard
  knowledge the reference's annotator added, not text extracted from this document.
- **Specific named vendors sometimes do appear**, but scattered deep in narrative
  procedure text with no predictable location: C4601003 names LabCorp and the Karius Test
  in sections 4.2.5.3 and 8.3.3.2 (a lab-testing methodology paragraph), not a vendor list.
  "Florence" (an eISF/document-transfer platform) appears in a data-security sentence in
  every study checked, not as a named organisation in a table.

Given our grounding rule (every value must resolve to a verbatim quote, never inferred),
the generic-name portion of this category cannot be filled without fabricating text that
is not in the source. The specific-name portion would need narrative-wide entity spotting
with a high false-positive risk (any proper noun could be mistaken for a vendor) for a
small, unpredictable yield. Deferred pending the audited gold set (Q-4), which should say
whether "vendors" in the gold standard is meant to be grounded in the protocol PDF at all.

## Objectives/endpoints reader (C-5): a reference-paraphrase finding

Checked every endpoint miss on 3 studies against the actual protocol table
(`spikes/_obj_bestmatch.py`, `spikes/_obj_diff.py`), cell by cell:

- **C5091017** (the study the readers were built against): 10 of 11 reference endpoints
  match at 0.5-1.0 Jaccard. The extraction is correctly reading the Objectives/Endpoints/
  Estimands table.
- **C4601003 and C4891001** (unseen during development): most misses are the *same*
  endpoint, worded differently — verified against the source PDF cell by cell:
  - C4601003: our endpoint is the table's own **Endpoints** column text verbatim
    ("Clinically- and laboratory-confirmed Lyme disease..."); the reference's endpoint text
    ("Incidence of clinically- and laboratory-confirmed Lyme disease...", "Proportion of
    participants reporting...") is closer to the table's separate **Estimands** column,
    which states the measurable statistic. The reference appears to synthesise endpoint +
    estimand, not transcribe the Endpoints column.
  - C4891001: the protocol's own Endpoints column reads "**QTc**" — nothing more; the
    reference's endpoint ("QTc interval (e.g., QTcF) as measured by triplicate ECGs...")
    is pulled from a different section of the protocol (a QTc sub-study), not the table.
    Same pattern for "OR" (the protocol's own abbreviation) vs the reference's expansion
    "Objective Response Rate (ORR)".

**No mechanical extraction bug was found in the cases checked** — the reader faithfully
transcribes the source table. The gap on unseen studies is the reference enriching or
correcting the table text with information the extractor cannot see without leaving the
grounding contract (a verbatim quote, never an inferred or synthesised one). This is the
same shape of finding as vendors above: it caps what a *grounded* score can show, and
only the audited gold set (Q-4) can say whether "endpoint" should mean the table's own
text or the reference's synthesised metric statement.
