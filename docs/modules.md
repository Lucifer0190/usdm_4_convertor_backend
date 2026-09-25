# Module reference

The package lives under `src/usdm4_assure/`. This page tracks both what exists today and
the target v0.3 layout from [`../DESIGN.md`](../DESIGN.md) §6 — planned modules are marked
*(planned, vN.N)*, and each names the DESIGN.md layer it belongs to.

> **v0.3 note on stub packages.** v0.2 shipped seven empty 1-line placeholder packages
> (`registry/`, `coding/`, `learn/`, `graph/`, `retrieve/`, `review/`, `eval/`) to make the
> layer map visible in the tree. The evidence review flagged this as a real risk — it made
> the design doc look more built than the code was. Going forward, **a package is only
> created once it has real code**; this page lists planned modules by name and target
> location instead, and CI now fails on empty packages.

## L0 — Substrate

| Module | Role |
|---|---|
| `ingest/pdf.py` | `ingest()` — PDF → `Document` (positioned blocks + rendered page images + character-level bboxes) via PyMuPDF. Deterministic, no LLM. Character geometry is what L5 grounding resolves quotes against. |

## L1–L2 — Layout, tables, SoA stitching *(v0.3 Phase 2, CP2-A–C)*

| Module | Role |
|---|---|
| `layout/base.py` | Common `TableGrid`/`CellSpan` IR every engine adapter returns. |
| `layout/pymupdf_adapter.py` | PyMuPDF `find_tables()` wrapped as a `TableGrid` source. Always on. |
| `layout/docling_adapter.py` | Docling integration — page layout, reading order. Optional (`[layout]` extra); returns `[]` if not installed. |
| `layout/mineru_adapter.py` | MinerU2.5 integration — table grid structure (beats frontier VLMs on TEDS). Optional; returns `[]` if not installed. |
| `soa/stitch.py` | The multi-page Schedule-of-Activities stitcher — header-signature matching across pages, "(continued)" detection, column-alignment reconciliation. No existing tool does this correctly (Docling doesn't merge, MinerU drops continuation content); it is the architecture's declared risk centre. Ambiguous page breaks become an ERROR `Finding` and are left unmerged rather than guessed. |
| `soa/continuation.py` | The per-page-break signal evaluation (`classify()`) the stitcher's chain-building loop calls. |
| `soa/from_stitched.py` | Bridges a `StitchedGrid` into the legacy 3-header-row `SoAGrid` shape the crossval/assembly path already consumes. Returns `None` (never a guess) when a table's confirmed header isn't exactly 3 rows. |
| `soa/grid_agreement.py` | Cross-engine structural agreement signal (task 2.4): cell-wise comparison between two engines' `TableGrid`s over their shared region; disagreement routes a cell to the vision pass. `has_signal=False` when fewer than two engines produced a grid. |
| `soa/vision_cells.py` | Frontier VLM cell-content pass (task 2.5): crops each activity-row data cell via PyMuPDF `clip`, reads it with the `vision` role, escalates to a different-family `vision_alt` only on disagreement with the grid's own parsed text. |
| `soa/rederive.py` | Mechanical mark-matrix re-derivation (task 2.6): an independent second read of "is this cell marked", scanning raw character geometry (`Document.chars`) for a mark glyph inside the cell's bbox — never the table parser's own cell text. |
| `soa/corrections.py` | Append-only `corrections.json` sidecar recording `rederive` disagreements per source PDF. Never mutates the raw `StitchedGrid`/`SoAGrid`. |

## L3 — Routing *(v0.3 Phase 3, CP3-A–C)*

| Module | Role |
|---|---|
| `sections/classify.py` | Deterministic title→taxonomy classifier (`config/section_taxonomy.yaml`), keyed on a section's own title words (not ICH section numbers, which older sponsor templates don't follow) with parent inheritance: `appendix` is a sticky type, `amendment_history` a sticky subtype. |
| `sections/graph.py` | Section graph from the PDF outline or numbered/unnumbered heading blocks — whichever source types more sections. `SectionGraph.section_for(page, y)` locates the innermost open section for any block. The `route`-role LLM is asked only about untyped residue (`classify_residue`), and only a taxonomy label is accepted back. |
| `sections/fingerprint.py` | Study-family classification: the first of 19 protocol families in `config/protocol_families.yaml` whose detection signal (title page / section titles / parsed phases) matches; the default family is kept but flagged with low confidence when nothing matches. |
| `sections/plan.py` / `sections/_ported_routes.py` | `build_plan()` feeds the fingerprint into the ported `StudyExtractionPlan` generator (primary/supporting/**prohibited** evidence scopes per domain) and exposes a stable `plan_hash` for the audit trail. |
| `extract/windows.py` | `window_for(doc, routed, domain)` filters a domain's `Document` down to its route's allowed scopes, plus a currentness guard (amendment-history and historic SoA/amendment surfaces are always excluded, on every domain but `amendments`) that the ported prohibited-scopes alone don't catch — the reference's historic prohibitions name a `source_surfaces` axis this graph doesn't populate. Filtered sections become `SCOPE` findings; a missing section graph is a `WARNING`, not silence. |

*The section title classifier and the currentness guard are ours; the route-mapping tables
in `sections/_ported_*.py` are near-verbatim ports (DEVPLAN.md's porting rule — no tests of
their own).*

## L4 — Extraction

| Module | Role |
|---|---|
| `extract/metadata.py` | **C1** — study title, acronym, sponsor, phase, identifiers, version. Two independent deterministic methods (`labels`, `titlepage`) plus an optional LLM member. |
| `extract/design.py` | **C2** — study type, intervention model, and arms (parsed from the randomization sentence), with arm types. |
| `extract/eligibility.py` | **C3** — inclusion/exclusion criteria (stored as free text per USDM), planned age range, sex. |
| `extract/objectives.py` | **C4** — primary/secondary objectives and endpoints (Estimands deferred to Phase 6). |
| `extract/soa/methods.py` | SoA table extractors: `pdfplumber` and `pymupdf` (single-page-only, kept for cross-validation diversity), `pymupdf_stitched` (multi-page-aware, via `soa/stitch.py` + `soa/from_stitched.py` — the ensemble member `pipeline.py`/`convert-soa` prefer, falling back to `pymupdf` when a table's header isn't the 3-row shape), and `vision` (frontier VLM cell-content pass, `soa/vision_cells.py`). |
| `extract/soa/crossval.py` | Cell-by-cell cross-validation → `AssuredGrid` with provenance tags. |
| `extract/soa/grid.py` | The SoA intermediate representation (`SoAGrid`, `AssuredCell`, `AssuredGrid`). |

*Under Phase 4 every call here will be sharded to <40 fields and use two-pass (free-text
reasoning, then constrained JSON) emission — see DESIGN.md §3 L4.*

## L5 — Grounding

| Module | Role |
|---|---|
| `ingest/geometry.py` | Per-page character-level geometry: glyph ↔ bbox mapping via PyMuPDF `get_text("rawdict")`. Character offsets in `Document.text_of(page)` directly index `Document.chars[page]` for deterministic quote resolution. |
| `ground/quote.py` | Resolves a candidate's verbatim quote to page + character offset + bounding box using character geometry. Pass 1: exact substring per page. Pass 2: normalized (whitespace collapse, ligatures, soft hyphens, smart quotes). Returns `Quote(text, verify_pass∈{exact,normalized,failed}, page, char_start, char_end, bbox)`. |
| `audit/store.py` | Append-only Part 11 audit store (SQLite). Every field decision logs model ID, prompt hash, quote text, verify_pass, page, and bbox for reproducibility and audit compliance. |

## L6 — Assurance ★

| Module | Role |
|---|---|
| `assure/__init__.py` | The moat. `assure()` groups candidates per field (ensemble), resolves grounding via L5, verifies each value against its source span, and computes confidence + `Decision`. Runs fully without an LLM on deterministic ensemble members; LLM is invoked only for verification on the uncertain subset. Uniform across C1–C4 and SoA. |
| `assure/verify.py` | Two-tier verifier: (1) deterministic token-overlap check (free); (2) escalation to a `verify`-role LLM (third family, different from extractor and alt-extractor) only when deterministic verdict is "partial". Hard gates: value with only failed quotes BLOCKs; value with ≥1 ok quote proceeds. |
| `extract/shards.py` | Shard definitions for two-pass LLM extraction: <40 fields per shard, organized by domain (C1–C4). Each shard has versioned `pass1.md` (reasoning) and `pass2.md` (JSON) templates. |
| `llm/two_pass.py` | Two-pass extraction orchestrator: pass 1 free-text reasoning, pass 2 strict JSON `[{field, value, quote}]` with mandatory verbatim quotes. `extract_shard()` returns `GroundedCandidate`s with resolved quotes. |
| `audit/writer.py` | Pipeline integration for audit logging: `write_field_decision()` appends one `AuditRecord` per `AssuredField`, pulling model/prompt/quote provenance from the winning grounded candidate. |
| `assure/features.py` | Multi-signal feature table (task 4.2) feeding the Phase 4 confidence model: verify_pass, verifier verdict, exact + fuzzy cross-candidate agreement, field type, a retrieval proxy (evidence-window kept ratio + route-plan hash), table-cell/grid-agreement flags (SoA), span length, page position, and `has_text_layer` — a real, deterministic "would OCR have been needed" signal (no OCR detector exists, so this is not dressed up as one). `write_features()` emits `features.parquet` (JSON Lines fallback without `pandas`/`pyarrow`). |
| `assure/confidence.py` | Calibrated confidence (task 4.3): L2-regularised logistic regression over `assure/features.py`'s table (pure numpy), then Platt recalibration fitted on *out-of-fold* logits — leave-one-protocol-out when protocol ids are given, K-fold otherwise, in-sample only when there is too little data (recorded as `platt_mode`, not hidden). Deterministic, with a `model_hash` over every parameter; `training_pairs()` joins features to scored labels; `brier()` is the headline calibration metric. |
| `assure/conformal.py` | Certified auto-accept threshold (task 4.3). Guarantee, exactly: with probability ≥ 1 − δ over the calibration draw, the rate of incorrect fields among those auto-accepted is ≤ α — marginal (pooled over field types), and void when exchangeability fails. Learn-then-Test fixed-sequence testing with exact binomial (Clopper–Pearson / Beta) p-values — the small-sample correction — over a threshold order fixed independently of the calibration set (`plan_sequence()` orders by estimated pass probability on an independent reference set). Refuses rather than guesses: < 47 calibration points, no certifiable threshold, or a protocol outside the calibration strata (`ConformalBound.for_protocol`). `gate()` triages fields on the bound (never lifts a `BLOCK`, auto-accepts nothing without a bound); `risk_coverage()` / `aurc()` are the deployment metrics. Bound + model hash are logged via `audit.write_calibration()` and per field in `verification["conformal"]`. |
| `assure/completeness.py` | Expected-vs-found reconciliation per domain: arm count vs. randomization ratio, arms×epochs cell coverage in the assembled study, SoA schedule-link integrity, protocol-text visit references vs. SoA columns, footnote markers vs. definitions, objective/endpoint pairing, eligibility list presence. A mismatch is a `COMPLETENESS` finding (`ERROR` demotes that domain's `auto_accept` fields to `review` via `demote_on_error()`); a rule with nothing to compare against stays quiet. |

## L7 — Assembly

| Module | Role |
|---|---|
| `assemble/metadata.py` | Patch assured metadata into a minimal conformant USDM skeleton (used by the C1 spine). |
| `assemble/soa.py` | `AssuredGrid` → `TimelineInput` → USDM ScheduleTimeline entities via the data4knowledge `TimelineAssembler`. |
| `assemble/study.py` | Compose the full `AssemblerInput` from every domain and run the top-level `Assembler` → one USDM 4.0 study. |
| `assemble/sanitizer.py` *(planned)* | Enforces the Assembler's implicit input contract before `execute()` — no empty required strings, valid role keys, well-formed enrollment blocks. Sanitizer repairs are logged as quality findings. |
| `assemble/builder_fallback.py` *(planned)* | Per-section fallback to `usdm4.builder` when the Assembler errors on a section, with the run's assembler-reliance ratio recorded. |

## L8 — Validation

| Module | Role |
|---|---|
| `validate/gate.py` | The conformance gates: pydantic structural, d4k rule engine (offline), CDISC CORE (optional, needs API key). |
| `validate/rule_map.py` *(planned)* | Declarative `rule_id → (domain, field, repair action)` table bridging validation findings to targeted re-extraction. |
| `repair/loop.py` *(planned)* | Bounded (≤2 round) repair loop driven by `rule_map.py`; unresolved findings become `review`/`block`, never silently dropped. |

## L9 — Certification *(planned, v0.3 Phase 5)*

| Module | Role |
|---|---|
| `review/` | Provenance review UI — click-to-source evidence crops, SME sign-off. |
| `review/audit.py` | Part 11 audit trail: model+prompt version, timestamps, prior values, reason-for-change, signature meaning, per field. |

## Model orchestration

| Module | Role |
|---|---|
| `llm/base.py` | The `LLM` protocol and tiered model routing (`ModelTier`, `tier_for`). |
| `llm/claude.py` | Claude adapter — pinned model ids per tier, extended-thinking budgets; activates when `ANTHROPIC_API_KEY` is set. |
| `llm/openrouter.py` | OpenRouter gateway — one key, many models, tiered (Haiku/Sonnet/Opus-equivalent), overridable per role. The default LLM path. |
| `llm/router.py` | `get_llm()` resolves OpenRouter → direct Anthropic → stub; `get_slm()` returns a cheap different-family model for ensemble diversity. |

*Note: logprobs are never load-bearing here — OpenRouter does not guarantee every provider
returns them (Anthropic does not). See DESIGN.md §4.*

## Deferred (recorded, not stubbed)

Neo4j graph store, closed-loop SLM fine-tuning at scale, and Merkle/replay audit receipts
are deliberately deferred per `PLAN.md` §7 — they are valuable Phase-2+ investments, not
Phase-0/1 scope, and are not represented as empty packages in the tree.

## Evaluation

| Module | Role |
|---|---|
| `eval/corpus.py` | usdm_data protocol-PDF loader (`spikes/_work/usdm_data`, gitignored): one `Study(study_id, pdf_path)` per directory whose source PDF matches the directory name (excludes `_USDM`/`_CRF`/`_SoA` derivatives). |
| `eval/run.py` | Phase 3 exit measurement: runs `run_full()` with routing on and off per study and diffs `AssuredField`s (value + decision) domain-by-field, writing `summary.md`/`summary.json` and a per-study diff. |
| `eval/labels.py` | Frozen ground truth (task 4.1): flattens a usdm_data USDM v4 wrapper JSON to one `FieldLabel` per (domain, field) at the same grain as `AssuredField`. Only 4 real corpus studies are both USDM v4 and non-synthetic (Alexion, CDISC Pilot, Eli Lilly NCT03421379, Sanofi); their labels live in `data/labels/fields/*.jsonl`, frozen and held out from earlier phases' tuning. `write_labels()` refuses to overwrite without `force=True`. |
| `eval/score.py` | Typed scorer: `exact` → `normalized` → `fuzzy` (token-overlap for `long_text`, numeric tolerance for `number`; `scalar` fields are not graded on a curve — a near-miss scalar is a `miss`) → `miss`. `summarize()` gives per-domain accuracy including accuracy-of-found (excludes fields the pipeline didn't even attempt). |
| `eval/report.py` | `usdm4 eval` scoreboard (task 4.4): runs `run_full()` on every labelled corpus study, scores the output, and reports the two numbers DESIGN.md L6 asks every run for — auto-accept coverage and review burden — plus realized error (the fraction of *labelled* auto-accepted fields that were actually wrong; a small-sample result, not the conformal bound's certified guarantee). Writes `eval_scoreboard.md`/`.json`, overall and per domain. |

## Orchestration & CLI

| Module | Role |
|---|---|
| `pipeline.py` | `run()` (metadata spine) and `run_full()` (full loop). Both now route all domains through the uniform `assure()` path and write `review.json` with page + bbox + verify_pass on every row. `run_full(routing=...)` builds a section-graph route plan and scopes each domain's evidence window (default on); `routing=False` is the eval harness's unrouted arm. |
| `cli.py` | `usdm4 version` — print version. `usdm4 roles` — print active model roles from `config/models.yaml`. `usdm4 convert` (metadata spine), `convert-soa` (table-only), `convert-full` (all domains). All accept `--require-llm` to fail on missing API key and `--core` to run CDISC CORE gate. `usdm4 eval` (task 4.4) scores the pipeline against the frozen field labels and prints/writes the scoreboard. |
| `contracts.py` | Shared dataclasses: `Document`, `FieldCandidate` (legacy), `GroundedCandidate` (quote-backed), `Quote`, `CharSpan`, `AssuredField`, `Finding`, `AuditRecord`, `Decision`. |
