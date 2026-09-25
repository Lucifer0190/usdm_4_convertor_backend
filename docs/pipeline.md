# Pipeline & data-flow contracts

> **v0.3 note.** This page describes the ten-layer pipeline (see
> [Architecture](architecture.md)). The implementation is being built in the phases
> described in [`../PLAN.md`](../PLAN.md). As of Phase 3 (CP3-C, 2026-09-25), the
> implemented layers are L0 (ingest), L1–L2 (layout + multi-page SoA stitching), L3
> (routing), L4 (sharded extraction), L5 (grounding), L6 (assurance + completeness),
> L7 (assembly), and L8 (validation). L9 is scheduled for Phase 5.

Two entry points, both in `usdm4_assure.pipeline`:

- `run(pdf)` — the metadata-only spine (C1). The smallest slice that touches every layer.
- `run_full(pdf)` — the full loop across metadata (C1), design (C2), eligibility (C3),
  objectives (C4), and the Schedule of Activities.

## Current data flow

```
PDF
 │  ingest.pdf.ingest()                         → Document
 ▼
Document ──  sections.plan.build_plan()          → RoutedDocument (graph + route plan)
           │
           ├─ extract.windows.window_for(...,"metadata")    → EvidenceWindow
           │      └─ extract.metadata.extract_all()          → list[FieldCandidate]
           │             └─ assure.assure()                  → list[AssuredField]   (C1)
           ├─ extract.windows.window_for(...,"design")       → EvidenceWindow
           │      └─ extract.design.extract_design()         → DesignExtract        (C2)
           ├─ extract.windows.window_for(...,"eligibility")  → EvidenceWindow
           │      └─ extract.eligibility.extract_*()         → EligibilityExtract   (C3)
           ├─ extract.windows.window_for(...,"objectives")   → EvidenceWindow
           │      └─ extract.objectives.extract_*()          → ObjectivesExtract    (C4)
           └─ extract.soa.methods (×2)           → SoAGrid, SoAGrid
                  │  (pdfplumber; pymupdf_stitched via soa.stitch, falling
                  │   back to single-page pymupdf when the header isn't a
                  │   confirmed 3-row shape)
                  └─ extract.soa.crossval        → AssuredGrid          (SoA)
 ▼
assemble.study.build_full_study(...)             → USDM 4.0 wrapper dict
 │      (data4knowledge Assembler + TimelineAssembler)
 ├─ assure.completeness.account(...)             → list[Finding]  (expected vs. found)
 │      └─ demote_on_error(...)                  → ERROR findings demote that domain's auto_accepts
 ▼
validate.gate.validate_wrapper(...)              → {structural, d4k, core}
 ▼
data/out_full/study.usdm.json, review.json (fields + findings + routing summary)
```

`run_full(routing=False)` skips the plan/window step and gives every extractor the whole
document — the eval harness's (`eval/run.py`) unrouted comparison arm.

**Phase 1 complete:** as of CP1-C, `assure()` is uniform across C1–C4 (all domains) and SoA,
applying the shared ensemble/grounding/verifier path per [`../DESIGN.md`](../DESIGN.md)
§3 L5–L6. Every field carries a resolved quote (page + character offset + bbox), and a value
with only a failed quote is a hard BLOCK.

**Phase 2 complete:** as of CP2-C, the SoA path is multi-page-aware. `soa/stitch.py` joins
tables across page breaks (loud `Finding` on ambiguity, never a silent guess);
`soa/grid_agreement.py` gives a cross-engine structural signal ahead of any model call;
`soa/vision_cells.py` reads cell content with a frontier VLM, cross-checked by a
different-family model only on disagreement; `soa/rederive.py` independently re-derives the
mark matrix from character-glyph geometry (never the table parser's own cell text) and
records any disagreement to `soa/corrections.py`'s sidecar without touching the raw grid.

**Phase 3 complete:** as of CP3-C, routing is live. `sections/graph.py` builds a section
graph from the PDF outline or numbered/unnumbered heading blocks (title-keyword
classification, not ICH section numbers — those break on older sponsor templates);
`sections/fingerprint.py` picks a protocol family from `config/protocol_families.yaml`'s
detection signals; `sections/plan.py` feeds that into the ported route planner. Every
domain's evidence is filtered through `extract/windows.py` to its route's allowed scopes,
plus a currentness guard that keeps amendment-history and historic-SoA text out of every
domain but `amendments` — `tests/test_scope_leak.py` demonstrates a superseded 3-arm design
leaking into the extracted study without routing, and not with it. `assure/completeness.py`
closes the loop with expected-vs-found accounting (arm counts, SoA schedule links, objective/
endpoint pairing), demoting a domain's `auto_accept` fields to `review` on an `ERROR` finding.
`eval/run.py` runs the routing-on/off comparison for the Phase 3 exit measurement.

## Target data flow (v0.3, in progress)

```
PDF
 │  L0  ingest: PyMuPDF text layer + char bboxes + page images
 ▼
Document
 │  L1  layout + table grids (Docling ∥ MinerU2.5)
 │  L2  multi-page SoA stitching (custom)
 ▼
RoutedDocument
 │  L3  section graph + study fingerprint + prohibited scopes
 ▼
ExtractionPlan
 │  L4  sharded per-domain extraction (<40 fields/call), two-pass emission
 ▼
list[FieldCandidate]  (each carries a verbatim quote, no candidate is ungrounded)
 │  L5  grounding: quote → page/char/bbox, exact-substring hard gate
 ▼
list[GroundedCandidate]
 │  L6  multi-signal confidence → conformal threshold → completeness check → triage
 ▼
list[AssuredField] / AssuredGrid
 │  L7  input sanitizer → usdm4 Assembler → per-section builder fallback
 ▼
USDM 4.0 wrapper
 │  L8  pydantic → d4k rules → CDISC CORE, rule→repair map, bounded repair
 ▼
Validated study + findings
 │  L9  review UI, SME sign-off, Part 11 audit trail
 ▼
Certified study.usdm.json
```

## The shared contracts (current)

Defined in `usdm4_assure.contracts`. These are the vocabulary every layer speaks today;
they extend (not replace) as L5's grounding and L6's conformal/completeness fields land.

### Foundation

- **`Block`** — one positioned text block: `text`, `page`, `bbox`, `kind`
  (`prose | heading | table | footnote`).
- **`Document`** — the deterministic ingest result: `source`, `blocks`, `full_text`,
  `page_images`. `head_text(n)` returns the first *n* pages, where metadata usually lives.

### Extraction → Assurance

- **`FieldCandidate`** — one value for one field from **one** method:
  `field`, `value`, `method`, `source_text`, `source_page`. Under v0.3, `source_text`
  becomes the mandatory verbatim quote that L5 resolves and verifies — a candidate without
  a verifiable quote cannot become an `AssuredField`.
- **`AssuredField`** — a field after Assurance: the chosen `value`, all `candidates`,
  whether methods agreed, the `verifier` verdict, a calibrated `confidence`, and a
  `Decision` (`auto_accept | review | block`). `as_review_row()` renders it for the
  review surface.

### SoA (in `extract/soa/grid.py`)

- **`SoAGrid`** — one method's view of the table: `epochs`, `visits`, `timings`,
  `activities`, `cells` (set of `(activity_i, visit_i)` marks), `footnote_activities`.
- **`AssuredCell`** — a cell after cross-validation: `present`, `provenance`
  (`both | <method>-only | none`), `confidence`, `decision`.
- **`AssuredGrid`** — the reconciled grid: the canonical labels plus a list of
  `AssuredCell`. `present_cells()` and `triage()` summarize it.

## Adding a domain

The architecture's payoff is that a new domain is additive, not a rewrite:

1. Write `extract/<domain>.py` returning `FieldCandidate`s (scalar fields) and/or a small
   structured dataclass (lists like arms/criteria), each candidate carrying a verbatim
   quote from its source.
2. Pass the candidates through `assure.assure()` to get `AssuredField`s — **every** domain
   goes through the shared path; there is no ad-hoc confidence anymore under v0.3.
3. Declare the domain's completeness expectations (§L6) so silent gaps surface as findings.
4. Map the assured output into the `AssemblerInput` in `assemble/study.py`.
5. Re-run `run_full` and check the [conformance](conformance.md) report.

No changes to the Grounding layer, the Assurance layer, the assembler, or the gates are
required.
