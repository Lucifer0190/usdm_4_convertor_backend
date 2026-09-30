# Conformance & limitations

This page documents the validation gates, the current results on the reference fixture,
and an honest analysis of what is and isn't achievable today — including the parts gated
by the upstream assembler rather than by our extraction. For measurements across the full
usdm_data corpus (23 real protocols) rather than the one synthetic fixture below, see
[docs/scoreboard.md](scoreboard.md) (task 7.1, `spikes/run_core_corpus.py`).

> **v0.3 note — the "0 of 235" figure is now actually re-measured, not just flagged stale.**
> Earlier internal notes cited a spike run in which zero of 235 real protocols in a test
> corpus reached a successful assembly. That figure was stale even when first flagged (the
> currently vendored `usdm4` source already fixes two of the bugs that spike's findings doc
> lists as open), and Phase 7's full-corpus run confirms it: **23/23** usdm_data protocols
> assemble structurally-valid without an assembler error under the pinned version (`PINS.md`).
> Every one of them still fails at least one d4k rule — real protocols are far more varied
> than the single synthetic fixture this page otherwise reports against, and several rules
> that never appear on the fixture (`DDF00213`, `DDF00247`) fail on 13-15 of the 23 real
> studies. See [docs/scoreboard.md](scoreboard.md) for the corpus-wide rule-failure histogram;
> those additional rules are not yet triaged into "our gap" vs. "upstream gap" the way the
> fixture's rules below are — that triage is the natural next increment past this page.

## The three gates

`validate/gate.py` runs up to three gates against an assembled study:

1. **Structural (pydantic)** — the study must load into the `usdm4` pydantic model.
   Non-negotiable; if it fails, the rule gates are skipped because they need a valid tree.
2. **d4k rule engine** — the bundled data4knowledge rule library (213 rules). Runs
   **offline**, no API key. This is the day-to-day gate.
3. **CDISC CORE** — the official engine (`cdisc-rules-engine`), wrapped by `usdm4`.
   Optional; requires a free `CDISC_LIBRARY_API_KEY` to download rules + controlled
   terminology. Enable with `convert-full --core`.

## Current results (reference fixture)

Running `convert-full` on `spikes/make_full_fixture.py` (a synthetic protocol spanning
metadata, design, eligibility, objectives, and a Schedule of Activities):

| Metric | Value |
|---|---|
| Structural gate | **PASS** |
| Assembler errors | **0** |
| d4k findings | **9** (down from 22 before Phase 6) |
| d4k failing rules | **5** (down from 12) |
| Entities | 3 arms, 3 epochs, 5 encounters, 5 activities, 5 scheduled instances |
| Phase | resolved to CDISC `C15601` (Phase II Trial) |

Adding domains demonstrably clears rules: `DDF00097` (planned age range) cleared by the
eligibility demographics, `DDF00213` (interventions expected for a parallel design) cleared
by the derived interventions, and Phase 6 (tasks 6.1–6.5) cleared `DDF00084`/`DDF00041`
(objectives attachment), `DDF00172`/`DDF00201` (sponsor identity/role), `DDF00006`/`DDF00025`
(timing windows), `DDF00153` (planned duration), and `DDF00087`/`DDF00088` (linked-list
ordering) — see below for exactly how, and why two of those were assumed to be pure
assembler bugs (Bucket 1) until they turned out to be fixable from our side after all.

## Why the study is not yet CORE-clean — and where the blocker is

**Phase 6 (CP6-A/B) closed six of the nine rules this page used to call "Bucket 1/2/3", and
found that two of them were never assembler bugs at all.** The lesson worth stating plainly:
"the assembler doesn't do X" needs to be checked against the real assembled objects and the
real rule engine before it's trusted, not inferred from a failing-rules list alone —
`assemble/fallback.py`'s `repair_timeline()` and `assemble/sites.py` are what actually fixed
these, none of them by extracting more data:

- **`DDF00084`/`DDF00041` (objective attachment) and `DDF00172`/`DDF00201` (sponsor identity
  /role)** were genuinely fixable from our input, not the assembler — see `assemble/sanitize.py`
  and `assemble/study.py`'s sponsor-scope fix (task 6.3). The sponsor's identifier scope was
  `{"standard": "sponsor"}`, an invalid value (`standard` only accepts registry/regulator
  keys); the assembler silently dropped the identifier, organisation and role as a result.
- **`DDF00006`/`DDF00025` (timing windows)** were never a missing-data problem: supplying
  `windows: {"items": []}` makes `TimelineAssembler` fall into its own out-of-range `"???"`
  placeholder for every timing, which reads as a *defined but incomplete* window — confirmed
  against the live d4k engine. The fix is one all-zero `Window` per timepoint, not real
  tolerance data (task 6.5, `soa/timing.py`).
- **`DDF00153` (planned duration) and `DDF00087`/`DDF00088` (linked-list ordering)** have no
  input field at all (`plannedDuration` is hardcoded `None`; `Encounter`/`StudyEpoch` are
  never `double_link`-ed, only `Activity` is) — both set directly on the assembled objects
  after `execute()` returns (task 6.5, `assemble/soa.repair_timeline()`).

### What is still failing, and why

| Rule(s) | Requirement | Status |
|---|---|---|
| `DDF00101` | An interventional study references an intervention from a procedure | Requires activity `definedProcedures` to reference interventions — not wired by the assembler; no extraction gap to close. |
| `DDF00140`, `DDF00200` | Organisation type from the CDISC organisation-type codelist | The sponsor's organisation type is not extracted; recorded honestly as CDISC `Unknown`, which the codelist itself doesn't include as a valid entry. |
| `DDF00031` | A non-anchor timing must point to two distinct scheduled instances | **A rule-library bug, confirmed live**: the check compares `Timing.type.decode` against the short string `"Fixed Reference"`, but the real decode `TimelineAssembler` produces is `"Fixed Reference Timing Type"` — the exact same code/decode mismatch `DDF00025`'s own fix history documents, just not applied here too. Not an extraction gap. |
| `DDF00075` | `biomedicalConceptIds`/`bcSurrogateIds`/etc. on activities | Investigated (task 6.5): offering an activity's own name as a biomedical concept does get a real exact-name match sometimes, but `TimelineAssembler`'s own procedure-creation path also mints a `Procedure` for every such name sharing one hardcoded placeholder LOINC code `"12345"` — trading this `WARNING` for a fabricated-code `ERROR` (`DDF00035`). Left as a documented gap rather than manufactured data. |

## Implication for the roadmap

Two rules remain genuinely gated upstream (`DDF00101`, `DDF00031`) and one needs richer
extraction this project doesn't attempt (`DDF00140`/`DDF00200`, sponsor organisation type;
`DDF00075`, biomedical concept coding — deliberately not forced, see above). None of the
three block a valid, CORE-submittable study; `validate/repair.py`'s `RULE_MAP` documents each
one's status and why it is not (yet, or ever, without upstream or added-scope work) fixed
from this project's side.

This is exactly the kind of maturity risk a proof-of-concept exists to surface: the
pipeline architecture is sound and the extractors work; full conformance depends partly
on the maturity of the open-source assembler we build on.

## Defining "conformant" honestly

Even CDISC's own USDM 4.0 sample fails 18 d4k rules. "Zero findings" is therefore not the
right bar for a single protocol in isolation. The right targets, per the project design,
are a **CORE pass rate against a pinned rule set + version**, with rules split into
*extraction-relevant* vs *narrative/display*, and a documented human-review step for the
remainder.

Also pin the **errata revision**, not just the model and rule-set versions: 27 USDM v4.0
errata have already been published, some flipping a rule's severity between ERROR and
WARNING. Treat rule severity as data pulled from a pinned source, not a hardcoded constant.
See [References](references.md) and [`docs/ai/archive/PLAN-v0.3-evidence-and-roadmap.md`](docs/ai/archive/PLAN-v0.3-evidence-and-roadmap.md) §1.

All three pins — `usdm4` package version, CORE rule-set version, and errata revision — are
recorded together in [`../PINS.md`](../PINS.md), so a version bump is a visible, deliberate
decision rather than silent drift.

## d4k triage on real protocols (PLAN.md task C-11, 2026-09-30)

Every d4k failure on the five train studies, classified per instance with
`spikes/_d4k_triage.py` (rule text, class, attribute, message and path for each finding),
not from the failing-rules list alone. The fixture-based section above predates real data:
seven rules that never fired on the fixture fired on real protocols.

**Before: 12 failing rules. After the fixes below: 8, none of them our bug.** Train-set
accuracy was unaffected (43.1% -> 43.3%).

### Our bugs — fixed

| Rule | Level | Cause | Fix |
|---|---|---|---|
| `DDF00172` | Error | The compound code (C-6) was a second sponsor-scoped `StudyIdentifier` | Moved to usdm4's own compound-codes channel (`identification.other.compound_codes` -> StudyVersion extension `004`); the rubric reads it there |
| `DDF00140`/`DDF00200` (2 of 7 instances) | Error | The PIP number was scoped to usdm4's generic `other` organisation, type Unknown | Scoped to EMA (a PIP number is an EMA decision number) |
| `DDF00247` | Warning | Criteria text with raw `<`/`&` ("ANC <1500/mm3", "pericardial & peritoneal") is not XHTML | Escaped once in the sanitizer for criteria, objectives and endpoints |
| `DDF00213` | Warning | The assured intervention model never replaced the regex one, so a single-arm sub-study was delivered as "Parallel Study" | `extract/domains.py` now propagates it, as it already did for arms |
| `DDF00088` | Warning | A later table's own visit (a PK timepoint) was appended after follow-up, so epochs ran Treatment -> Follow-up -> Treatment | Placed after the last earlier visit of its epoch |

### Not our bugs — each with its reason

| Rule | Level | Studies | Classification | Why |
|---|---|---:|---|---|
| `DDF00031` | Error | 5/5 | **Rule-library bug** | Compares `Timing.type.decode` to `"Fixed Reference"`; the assembler's decode is `"Fixed Reference Timing Type"` (see above). |
| `DDF00084` | Error | 3/5 | **Rule vs protocol** | "Exactly one primary objective" — these protocols state 2-4 (efficacy, safety, immunogenicity; Phase 1b and Phase 2). The reference has the same count. Demoting a real primary objective would misstate the protocol. |
| `DDF00241` | Error | 5/5 | **Model limitation** | "18 years or older" has no maximum. USDM's `Range.maxValue` is required, DDF00097 requires a planned age range, and usdm4's assembler fills the missing maximum with the minimum — which its own DDF00241 then rejects. The only way to pass is to invent an upper age; not done. |
| `DDF00140`/`DDF00200` | Error | 5/5 (sponsor only) | **Data gap** | The sponsor's organisation type is not stated in the protocol; recorded as CDISC `Unknown`, which the codelist does not contain. The reference's "Drug Company" is domain knowledge, not protocol text. |
| `DDF00101` | Warning | 5/5 | **Upstream** | Needs procedures referencing interventions; the assembler does not wire them. |
| `DDF00075` | Warning | 5/5 | **Deliberate gap** | Biomedical-concept coding would mint placeholder LOINC codes (see above). |
| `DDF00174` | Warning | 2/5 | **Correct as is** | EMA holds both the EU CT and the PIP number — both are EMA-issued; the reference is identical. |

Remaining **errors** are therefore one rule-library bug, one protocol-vs-rule conflict, one
USDM model limitation and one data gap. CORE (C-12) has not been run: it needs
`CDISC_LIBRARY_API_KEY`, which is not configured.

## First real CORE run (PLAN.md task C-12, 2026-09-30)

The official CDISC CORE engine (`cdisc-rules-engine` 0.17.1, 205 USDM 4.0 rules executed) run on the
five train studies (`spikes/_core_run.py`, results in `data/out/<run>/core_results.json`). Each study
takes 10-20 s. Every study fails, with 230-400 findings across 30 rules.

**The headline number is not usable yet: terminology could not be loaded.** CDISC Library serves the
controlled-terminology packages as "Members-only content" (HTTP 401 with the free key; the rules
endpoint, 207 rules, works). CORE therefore ran with 0 terminology packages, and **1,336 of the 1,558
findings (23 of 31 rules)** are the single complaint "codeSystemVersion is not a valid terminology
package date" / "code or decode not in the codelist". Those cannot be judged as right or wrong until a
terminology source is available (CDISC membership, or CT packages supplied another way). Do not quote
the raw CORE count as a conformance result.

The 8 rules that do not depend on terminology, classified:

| CORE rule | d4k equivalent | Studies | Classification |
|---|---|---:|---|
| CORE-000871 (one primary objective) | DDF00084 | 3/5 | Rule vs protocol (see above) |
| CORE-001009 (age range min < max) | DDF00241 | 5/5 | USDM model limitation (see above) |
| CORE-001065 (intervention referenced by a procedure) | DDF00101 | 5/5 | Upstream: the assembler does not wire it |
| CORE-001076 (activity refers to a procedure/BC) | DDF00075 | 5/5 | Deliberate gap (no invented codes) |
| CORE-000938 (cardinality) | none | 3/5 | **Ours**: `Estimand.interventionIds` is empty when the estimand's treatment cannot be matched to an extracted intervention (`assemble/estimands.py`) |
| CORE-000971 (address has an attribute) | none | 5/5 | **Data gap, extractable**: the sponsor's organisation gets an empty address; page 1 states "Sponsor Legal Address: ..." and is not read |
| CORE-000873 / CORE-001068 (unique governance dates) | none | 5/5 | Unclear: the finding lists every value as "Not in dataset" while no dates are set, which looks like an engine artefact on an empty date list; unverified |

Not yet done: fixing CORE-000938 and CORE-000971 (both small, both ours), and re-running CORE once
terminology is available.

Also fixed: `validate/gate.py` summarised CORE with the d4k result shape and so reported it empty;
it now reads CORE's own result (`_summarize_core`).
