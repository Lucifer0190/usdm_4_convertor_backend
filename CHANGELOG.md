# Changelog

All notable changes to USDM4-Assure. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); this project is pre-release (0.x) and not
yet semantically versioned.

## [Unreleased]

### Phase 5 in progress — Review UI + certification (v0.3.5, CP5-A)

**Major milestone:** `run_full()` now writes a Part 11 audit trail — every field decision
was already designed for this (`contracts_audit.AuditRecord`, `audit/store.py`'s append-only
SQLite store, both built in Phase 1) but nothing had actually called them until now. An HTMX
review UI reads that trail: a reviewer sees every field sorted worst-first, expands a
click-to-source crop rendered straight from the PDF, edits a value with a required reason, and
certifies the run — every action a new, non-destructive audit record, never an overwrite.

Added:
- `pipeline.run_full()` writes one `AuditRecord` per final field decision (after completeness
  may have demoted one) to a per-source-PDF SQLite store, and records a `(sha256 -> pdf_path)`
  pointer (`audit.record_source()`) so later tools can find the PDF again from just its hash.
  `FullResult` now carries `source_sha256` and `run_id`.
- `audit.write_review_edit()` / `write_certification()` — new `AuditRecord` kinds for a
  reviewer's edit (`REVIEW_EDIT`, `method=HUMAN`, `decision=AUTO_ACCEPT`, prior value + reason)
  and a certification (`CERTIFY`, reviewer id + signature meaning). New `AuditEvent.CALIBRATION`
  sibling `AuditEvent.CERTIFY` was already defined; this is what writes it in practice.
- `review/app.py` — FastAPI + Jinja2 + HTMX UI (`templates/`): home page lists every source
  with audit history; source page lists current field values (the latest record per
  `(domain, field)`, whatever wrote it) sorted `block` → `review` → `auto_accept`, confidence
  ascending; click-to-source crops (`review/crops.py`, PyMuPDF, rendered on request); an edit
  form and a certify button, both HTMX partial-swapped. Localhost only, no auth — `docs/review.md`
  states why that is a scoped, deliberate decision.
- `review/telemetry.py` (task 5.2) — post-edit distance: normalized character edit distance
  between a field's original extraction and its value as of certification. Edited fields'
  certified values export to `data/labels/edits/<study>.jsonl` — real signal, but never the
  frozen `data/labels/fields/` ground truth (task 4.1); this directory is explicitly
  regenerable, not frozen.
- `docker-compose.yml` gains a `review` service (`--profile review`); the placeholder `neo4j`
  service is removed (PLAN.md's Phase-2+ deferrals — it was never scheduled, only parked).
- `docs/review.md`; new optional dependency group `review` (fastapi, uvicorn, jinja2,
  python-multipart); `httpx` added to `dev` for `fastapi.testclient`.

### Phase 4 complete — Confidence + conformal (v0.3.4, CP4-A–C)

**Major milestone:** field-level confidence is no longer a hand-set formula. Frozen labels
from 4 held-out usdm_data studies feed a typed scorer, a multi-signal feature table, a fitted
+ recalibrated confidence model, and a certified auto-accept threshold with an exact,
small-sample statistical guarantee — plus a scoreboard reporting all of it. The eval labelled
set (62 field labels) is far short of DESIGN.md §5's ~1,200-label target, so every number the
scoreboard prints says so explicitly rather than posing as a general accuracy claim.

CP4-C (task 4.4):
- `eval/report.py` / `usdm4 eval` — runs `run_full()` on every labelled corpus study, scores
  it, and reports auto-accept coverage, review burden and realized error (DESIGN.md L6),
  overall and per domain, to `eval_scoreboard.md`/`.json`.
- `eval/corpus.py`'s PDF discovery is more general: a directory with no `<dir>.pdf` now falls
  back to its one PDF every other PDF there is named after (`CDISC_Pilot_Study.pdf` +
  `CDISC_Pilot_Study_CRF.pdf`), fixing a real corpus study the exact-name convention missed
  entirely — task 4.4's first eval run surfaced this by failing to find it.

CP4-A (tasks 4.1-4.2):
- `eval/labels.py` — flattens a usdm_data USDM v4 wrapper JSON to frozen `FieldLabel`s at
  the same (domain, field) grain as `AssuredField`. Labels for the 4 real, USDM-v4 corpus
  studies (Alexion, CDISC Pilot, Eli Lilly NCT03421379, Sanofi) are committed at
  `data/labels/fields/*.jsonl`; `write_labels()` refuses to overwrite without `force=True`.
  These 4 studies are held out from Phases 0-3's tuning.
- `eval/score.py` — typed scorer: exact → normalized → fuzzy (token-overlap for prose
  fields, numeric tolerance for ages; short scalar fields are not graded on a curve) → miss.
  `summarize()` gives per-domain accuracy, including accuracy-of-found.
- `assure/features.py` — one `FeatureRow` per `AssuredField`: verify_pass, verifier verdict,
  exact + fuzzy cross-candidate agreement, field type, a retrieval proxy (evidence-window
  kept ratio + route-plan hash), table-cell/grid-agreement flags, span length, page position,
  and `has_text_layer` (a real deterministic signal, not an invented OCR classifier).
  `write_features()` emits `features.parquet` (JSON Lines fallback without pandas/pyarrow).
- `pipeline.FullResult.windows` — each domain's `EvidenceWindow`, exposed for `features.py`.
- `eval` optional dependency group (`pandas`, `pyarrow`).

CP4-B (task 4.3):
- `assure/confidence.py` — logistic confidence model + out-of-fold Platt recalibration
  (leave-one-protocol-out), deterministic `model_hash`, save/load with hash verification.
- `assure/conformal.py` — certified auto-accept threshold: with probability ≥ 1 − δ over the
  calibration draw, incorrect fields among auto-accepted ones are ≤ α (marginal; void on
  exchangeability breaks). Learn-then-Test fixed-sequence testing with exact binomial
  (Clopper–Pearson) p-values; refuses below 47 calibration points, when nothing certifies,
  or for a protocol outside the calibration strata. `gate()`, `risk_coverage()`, `aurc()`.
- `audit.write_calibration()` and `AuditEvent.CALIBRATION`; field records cite the bound's
  threshold, model hash and calibration-set hash.
- `numpy` is now a declared dependency (it was already present transitively).

### Phase 3 complete — Routing, prohibited scopes, completeness (v0.3.3, CP3-A–C)

**Major milestone:** every extraction domain now reads a section-graph-scoped view of the
document instead of the whole PDF. A section graph (from the PDF outline, or numbered and
unnumbered heading blocks when there is none) is classified onto the four-axis taxonomy by
title words — not ICH section numbers, which older sponsor templates don't follow — and a
protocol-family fingerprint drives the ported route planner. Each domain's evidence window
drops sections its route prohibits, plus a currentness guard that keeps amendment-history and
historic-SoA text out of every domain but `amendments`. `tests/test_scope_leak.py` documents
the failure this prevents: a front-matter amendment summary quoting the original 3-arm design
ahead of the current 2-arm design section — unscoped, the design extractor returns the old
arm count; scoped, the current one. `assure/completeness.py` adds expected-vs-found checks
(arm count vs. randomization ratio, SoA schedule-link integrity, objective/endpoint pairing,
eligibility list presence, …), demoting a domain's `auto_accept` fields to `review` on an
`ERROR` finding. `eval/run.py` runs the routing-on/off comparison across the usdm_data corpus.

Added:
- `sections/classify.py` — deterministic title→taxonomy classifier with parent inheritance
  (sticky `appendix` type, sticky `amendment_history` subtype).
- `sections/graph.py` — section graph from bookmarks or heading blocks; `classify_residue()`
  asks the `route`-role LLM only about untyped sections, accepting only taxonomy labels.
- `sections/fingerprint.py` — protocol-family detection from `config/protocol_families.yaml`
  signals (title page / section titles / parsed phases), with an honestly-flagged default.
- `sections/plan.py` — `build_plan()` wires the fingerprint into the ported
  `StudyExtractionPlan` generator and exposes a stable `plan_hash`.
- `extract/windows.py` — `EvidenceWindow` / `window_for()`: prohibited-scope filtering plus
  the currentness guard; filtered sections become `SCOPE` findings.
- `assure/completeness.py` — expected-vs-found reconciliation, `demote_on_error()`.
- `eval/corpus.py`, `eval/run.py` — usdm_data protocol-PDF loader and the routing on/off
  comparison harness.
- `sections/models.py`, `sections/_ported_routes.py`, `sections/_ported_pages.py`,
  `config/section_taxonomy.yaml`, `config/protocol_families.yaml` — near-verbatim ports from
  the reference extractor (route mapping, page-selection heuristics, taxonomy/family data).
  19 protocol families were kept faithfully to the source, correcting PLAN.md's "11".

Changed:
- `pipeline.run_full()` gained `routing: bool = True`; `AssuredField`s now come from a scoped
  `Document` per domain, and `review.json` carries the route plan hash, section-graph summary,
  and per-domain window/filtering detail.
- `audit/writer.py` records each field's `retrieval_config` (route + route-plan hash +
  filtered sections) for the Part 11 trail.
- `scripts/guard.py` exempts `_ported_*.py` files from the 400-line limit (they are sized by
  their source, not authored here).

### Phase 2 complete — Multi-page SoA (v0.3.2, CP2-C)

**Major milestone:** the Schedule of Activities path is now multi-page-aware end to end —
tables spanning page breaks stitch correctly, cell content gets a cross-checked frontier
VLM read, and the resulting mark matrix is independently verified against raw character
geometry before assembly. This is the architecture's declared "risk centre" (DESIGN.md L1–L2):
no existing tool (Docling, MinerU) merges a continued SoA table correctly.

Architecture layers now complete: L0–L2 (ingest, layout, multi-page SoA stitching), L4–L8
(extraction through validation). L3 (routing) and L9 (review UI) scheduled for Phases 3 and 5.

The following changes reflect this:
- **Common table IR** (`layout/base.py`, `layout/pymupdf_adapter.py`, `layout/docling_adapter.py`,
  `layout/mineru_adapter.py`) — `TableGrid`/`CellSpan` shared across engines. PyMuPDF is always
  on; Docling and MinerU2.5 are optional (`[layout]` extra) and degrade to `[]`, never a
  partial guess, when not installed.
- **Multi-page SoA stitcher** (`soa/stitch.py`, `soa/continuation.py`) — joins a table's
  continuation across a page break using header-row repetition, column x-alignment,
  "(continued)" cues, and page adjacency. Ambiguous breaks become an ERROR `Finding` and are
  left unmerged — the stitcher never guesses in either direction. Five hand-labelled
  real-world multi-page SoAs (`data/labels/soa/`) reproduce exactly.
- **Cross-engine structural agreement** (`soa/grid_agreement.py`) — cell-wise comparison
  between two engines' table grids over their shared region; disagreement routes that cell to
  the vision pass. Honestly reports `has_signal=False` rather than inventing agreement when
  only one engine produced a grid.
- **Frontier VLM cell-content pass** (`soa/vision_cells.py`, `llm/openrouter.py`'s new
  `complete_vision()`) — replaces the previous `extract_vision` no-op. Crops each cell from
  the source PDF, reads it with the `vision` role, escalates to a different-family
  `vision_alt` only where that reading disagrees with the grid's own parsed text.
- **Mechanical mark-matrix re-derivation** (`soa/rederive.py`) — a second, independent read of
  "is this cell marked" from raw character-glyph geometry (`Document.chars`), never the table
  parser's own cell text. Agrees with extraction's own claim on every cell across all five
  labelled SoAs. Disagreements are appended to a `corrections.json` sidecar
  (`soa/corrections.py`) that never overwrites the raw extraction.
- **`soa/from_stitched.py`** — bridges the multi-page-aware `StitchedGrid` into the legacy
  3-header-row `SoAGrid` shape the already-tested cross-validation/assembly path consumes.
  Returns `None` (never a guess) when a table's confirmed header isn't that shape.
- **Pipeline and CLI rewire** (`pipeline.py`, `cli.py`) — `run_full()` and `convert-soa` now
  use `extract_pymupdf_stitched` as the pymupdf ensemble member, falling back to the
  single-page `extract_pymupdf` only when the stitched grid can't be reduced to the 3-header
  shape.
- **Documentation** (`docs/pipeline.md`, `docs/modules.md`) — L1–L2 now documented as
  implemented, not planned.

### Phase 1 complete — Grounded spine (v0.3.1, CP1-C)

**Major milestone:** All four domains (C1 metadata, C2 design, C3 eligibility, C4 objectives)
now flow through a uniform Assurance path with **verbatim quote grounding**. Every emitted
field carries a resolved quote (page + character offset + bounding box), and a value with
only a failed quote is a hard BLOCK — no exceptions.

Architecture layers now complete: L0 (ingest with character geometry), L4–L6 (two-pass sharded
extraction with grounding and verification), L7–L8 (assembly and validation). Layers L1–L3
(layout, multi-page SoA stitching, routing) and L9 (review UI) scheduled for Phases 2–5.

The following changes reflect this:
- **Character-level geometry** (`ingest/geometry.py`) — PyMuPDF `get_text("rawdict")` + synthetic
  separators preserve a deterministic offset↔bbox mapping. Quote resolution is now code-emitted,
  never model-emitted.
- **Two-pass sharded LLM extraction** (`llm/two_pass.py`, `extract/shards.py`) — every field
  the model proposes carries a verbatim quote; pass 1 free-text reasoning, pass 2 strict JSON.
  Quote resolution (`ground/quote.py`) handles exact substring and normalized fallback
  (whitespace collapse, ligatures fi/fl, soft hyphens, smart/ASCII quotes). Failed quote =
  `Quote(verify_pass="failed")`, never a low-confidence guess.
- **Append-only Part 11 audit store** (`audit/store.py`, `audit/writer.py`) — every field
  decision logs model ID, prompt hash, quote, page, and bbox. SQLite triggers enforce immutability.
- **Uniform Assurance** (`assure/__init__.py`, `assure/verify.py`) — one path for all domains.
  Grounding is enforced before the verifier runs: a value backed only by failed quotes blocks
  before any other logic. Verifier is two-tier: deterministic token-overlap (free), then
  escalation to LLM `verify`-role (third family, only on uncertain subset). Runs fully without
  an LLM on deterministic members.
- **Pipeline rewire** (`pipeline.py`) — `run_full()` now routes C2, C3, C4 through `assure()`,
  writes `review.json` aggregating all domains with page + bbox + verify_pass on every row.
- **CLI** — new `usdm4 roles` command prints active model role mapping from `config/models.yaml`.
  `convert` and `convert-full` accept `--require-llm` to fail on missing API key.
- **Documentation** (`docs/pipeline.md`, `docs/modules.md`) — updated to reflect L5 grounding
  and L6 verification as implemented, not planned.

### Architecture (v0.3.1) — Frontier-only model strategy, verified live

**Major change:** v0.3 proposed SLM-tiered extraction (cheap small models like Llama-3.1-8B
and gpt-oss-20b for specific roles to cut cost). Re-analyzed the published evidence in
`PLAN.md` §4.2 and found that **frontier models outperform small models in every measured
domain**. Updated the strategy to accuracy-first: frontier LLMs are the default for all
roles, and SLMs are used only when empirically proven to beat frontier on that task. One
specialist survives this test: **MinerU2.5 beats Gemini-2.5-Pro on table structure (88.2 vs
85.7 TEDS).**

The following changes reflect this:
- Removed SLM ensemble member (Llama-3.1-8B) from the extraction path — cross-family
  verification now uses `openai/gpt-5.1` (different family, frontier accuracy).
- Removed cheap small-model routing (gpt-oss-20b for section classification) — deterministic
  signals (bookmarks, ToC, headings) now handle most routing; residue goes to frontier LLM.
- Removed `qwen3-vl-30b-a3b-instruct` SoA cell first-pass — frontier VLM now handles all
  cell extraction with cross-family checks.
- Documented cost control via disk cache (re-runs free after first pass) and verification
  on the uncertain subset only, not via model downgrade.
- Updated `PLAN.md` §4, `DESIGN.md` §4, `architecture.html` model tables, `docs/development.md`
  to reflect frontier-only roles in `config/models.yaml`.

Earlier verification (live catalog):
- Queried the live catalog (`GET /api/v1/models`, 444 models, 2026-09-17) and confirmed
  OpenRouter proxies only chat-completion APIs, not task-specific NER/NLI encoders or
  caller-uploaded fine-tuned checkpoints. `GLiNER-BioMed` and `MiniCheck-FT5` are
  **self-hosted**, not OpenRouter-served — a deliberate infrastructure decision.
- Verified frontier tier slugs against catalog: `anthropic/claude-sonnet-4.5`,
  `openai/gpt-5.1`, `google/gemini-3.1-pro-preview` (three families for cross-family
  verification).
- Confirmed logprobs support gap: `llama-3.1-8b-instruct` lists `logprobs`/`top_logprobs`;
  `claude-sonnet-4.5` does not.

### Architecture (v0.3)
- **Rewrote `DESIGN.md` and `docs/` against a published-literature review** (`PLAN.md`,
  new). Two v0.2 claims did not survive the review and are retracted rather than carried
  forward:
  - The "~89% field / ~76% SoA market ceiling" was not a matched benchmark. The 89%
    figure is a vendor-authored (Banting Health AI) n=23 study on a bespoke non-USDM
    schema with a partly-LLM-generated gold standard; the 76% figure (Kramer/MITRE
    ProtocolMiner, peer-reviewed, genuinely USDM-targeted) is a whole-table pass rate
    (22/29 protocols), not a field-level metric. Quoting them together implied a
    benchmark that does not exist.
  - "Two independent paths at ~89% each agree on ~80-85% of fields, raising precision to
    ~97-99% on the agreed set" assumed near-independent errors. Measured cross-model
    error correlation is 0.74-0.82 (GPT-4o/Claude 0.822), and 48% of mistakes replicate
    across model families. Ensemble agreement is retained as one input to a calibrated
    confidence model, not a precision guarantee.
- New architecture layers added to the design (not yet all implemented — see `PLAN.md`
  for phasing): a grounding layer (L5) that resolves every field to a verbatim,
  exact-substring-verified quote and page/character/bbox coordinates computed by code,
  never emitted by the model; a custom multi-page Schedule-of-Activities table stitcher
  (L2), since no available tool merges tables spanning multiple pages correctly; a
  completeness-accounting step (expected vs. found counts) as the direct defense against
  silent omission, the dominant failure mode on long documents; and a conformal-prediction
  bound on the auto-accepted field set, replacing the plan for a purely hand-tuned
  confidence formula.
- Vision-first SoA reframed as **specialist-grid + vision-LLM-content**: published
  evidence shows a 1.2B specialist table model beats frontier vision-LLMs on table
  *structure*, while vision-LLMs are stronger on *cell text* — no single model should own
  both.
- Recorded `usdm4`'s GPL-3.0 license as a deliberate, internal-use decision, and adopted
  `data4knowledge/usdm_data` (~20 real, CORE-validated studies with public source PDFs) as
  the ground-truth seed corpus in place of hand-labeling the 4 local protocol PDFs from
  scratch.
- Corrected a stale internal figure: an earlier spike's "0 of 235 protocols assembled"
  result is outdated against the currently vendored `usdm4` source, which already fixes
  two of that spike's "open" bugs. The real pass rate is unmeasured, not proven broken —
  re-measuring it is now Phase 0 of the roadmap.

### Added
- **SLM ensemble member** — `--slm` on `convert`/`convert-full` adds a cheap
  different-family small model (default `meta-llama/llama-3.1-8b-instruct`,
  `OPENROUTER_SLM_MODEL` to override) as an independent metadata member. On the reference
  fixture this took metadata from 5/6 to 6/6 auto-accept (SLM independently agreed with
  Claude on the study title). `extract_metadata` generalized to accept multiple LLM
  members; `router.get_slm()` added. *Finding: OpenRouter hosts no clinically fine-tuned
  model — a true clinical SLM needs the fine-tuning path, not an off-the-shelf slug.*
- **OpenRouter as the default LLM gateway** (`llm/openrouter.py`, `llm/config.py`) — one
  key (`OPEN_ROUTER_KEY`, loaded from `.env`), many models, Claude-first and tiered
  (Haiku / Sonnet 4.5 / Opus 4.8, overridable via `OPENROUTER_MODEL_*`). The router now
  resolves OpenRouter → direct Anthropic → stub. Verified live: the Claude ensemble member
  lifted metadata auto-accept from 1/6 to 5/6 on the reference fixture.
- **Deterministic test guard** — `tests/conftest.py` sets `USDM4_NO_LLM=1` so the suite
  never makes live/paid/non-deterministic LLM calls.
- **Documentation set** under `docs/` — architecture, pipeline & contracts, module
  reference, conformance & limitations, development, and references. Google-style
  docstrings on the public API. `CONTRIBUTING.md`, this changelog, and an `mkdocs.yml`.
- **C3 eligibility extractor** (`extract/eligibility.py`) — inclusion/exclusion criteria
  (free text), planned age range, and sex.
- **C4 objectives extractor** (`extract/objectives.py`) — primary/secondary objectives and
  endpoints.
- **Interventions** derived from arms in `assemble/study.py`, wired into the study design.
- **Full loop** (`pipeline.run_full`, `usdm4 convert-full`) — one protocol PDF → one
  USDM 4.0 study across metadata, design, eligibility, objectives, interventions, and SoA.
- **C2 design extractor** (`extract/design.py`) — study type, intervention model, and arms
  parsed from the randomization sentence.
- **SoA sub-pipeline** (`extract/soa/`) — two independent table engines (pdfplumber +
  PyMuPDF), cell-by-cell cross-validation with provenance tags, and assembly into USDM
  ScheduleTimeline entities via the data4knowledge `TimelineAssembler`.
- **Assurance layer** (`assure/`) — multi-method ensemble, grounded verifier, calibrated
  confidence, and per-field triage. Runs without an LLM.
- **Metadata spine** (C1) — `ingest` → `extract/metadata` → `assure` → `assemble` →
  `validate`, with a Claude adapter (`llm/`) that joins as an ensemble member when a key
  is present.
- **Conformance gates** (`validate/gate.py`) — structural (pydantic), d4k rules (offline),
  and CDISC CORE (optional). Docker setup for portability.

### Changed
- Conformance on the reference fixture improved from 24 → 22 d4k findings (14 → 12 failing
  rules) after adding C3/C4 + interventions (`DDF00097`, `DDF00213` cleared).

### Known limitations
- Not yet CORE-clean. A share of residual findings is gated by the upstream
  data4knowledge assembler (objectives not attached to the study design; sponsor role not
  emitted; procedure→intervention references). See `docs/conformance.md`.
- Eligibility is stored as free text (native Boolean-logic modelling is a USDM gap and an
  industry-wide ~30% task).
- Estimands, amendments, the review UI, closed-loop learning, and the Neo4j graph store
  are planned, not built.

## Spike (foundation)
- Proved the backbone: real USDM 4.0 instance loads into the `usdm4` pydantic model; d4k
  and CORE facades reachable; Python 3.12 constraint identified; fork base set to
  data4knowledge. See `spikes/SPIKE_LOG.md`.
