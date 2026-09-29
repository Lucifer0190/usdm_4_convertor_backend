# USDM4-Assure — Development Plan v0.3 (tiered by model + thinking level)

## Context

`PLAN.md` / `DESIGN.md` (v0.3) fix the architecture: ten layers L0–L9, OpenRouter as the
only LLM gateway, verbatim-quote grounding, a custom multi-page SoA stitcher, completeness
accounting, and a conformal confidence bound. What is missing is an **execution plan**: a
task list that says, for each task, which Claude model and thinking level to develop it
with, grouped so you switch models rarely, with a commit after every task.

This plan is derived from the repo inventory (what actually exists today) plus PLAN.md's
phases. Ground rules you set:

- **Accuracy decides model choice, never cost.** A small/specialist model is used only
  where published, task-matched evidence shows it *beats* the frontier LLM. "About equal
  but cheaper" does not qualify. Under that rule exactly one specialist survives
  (MinerU2.5 for table structure); every LLM role uses frontier models. See §M for the
  per-role analysis.
- **OpenRouter only, for now.** No self-hosted LLM serving. Self-hosted candidates are
  parked in §F and only return if Phase 4's eval shows a domain where they would beat the
  frontier model.
- **Rewant's logic is ported, not tested.** Files ported from
  `Rewant's_USDM_Extractor/app/services/` get no tests of their own. Tests cover only code
  we author (detectors, resolvers, stitcher, assurance, etc.).
- **Commit after every task** with the message given, push at each checkpoint (or every
  commit — both fine). Run `ruff check` + `pytest` before each commit.
- **I announce every checkpoint boundary** ("switch to Sonnet, thinking low") and stop
  until you've switched. Use `/compact` at checkpoint boundaries — each checkpoint lists
  exactly which files to read on entry so the fresh context stays small.

### Current state (inventory, 2026-09-17)

`src/usdm4_assure/` = 1,976 LOC. Real: `contracts.py`, `pipeline.py`, `cli.py`,
`ingest/pdf.py` (block-level bboxes only), `extract/{metadata,design,eligibility,objectives}.py`,
`extract/soa/{grid,methods,crossval}.py` (**first single-page table only; `extract_vision`
is a no-op**), `assure/__init__.py` (only metadata + SoA go through it), `assemble/*`,
`validate/gate.py`, `llm/{base,router,openrouter,claude,config}.py` (no cache, no retries).
Empty 1-line stubs to delete: `coding/ eval/ graph/ learn/ registry/ retrieve/ review/`.
No CI, no pre-commit, no SQLite/FastAPI/audit code. 18 offline tests on synthetic PDFs.
`usdm4` pinned only as `>=0.28.0`; vendored clone at `spikes/_work/usdm4-src` is 0.29.0 @ `ebf7cdb`.

---

## Tier legend (how to read each task)

| Tag | Use for | Why |
|---|---|---|
| **H / off** — Haiku, thinking off | verbatim ports, YAML/config, CI files, deleting stubs, docstrings, CHANGELOG/docs, boilerplate adapters | zero design decisions; cheapest tokens |
| **S / low** — Sonnet, thinking low | well-specified implementation with an obvious shape (loaders, CLI, scripts, straightforward tests) | Sonnet reads the spec and writes it; no deliberation needed |
| **S / med** — Sonnet, thinking medium | implementation with a few local decisions (prompt design, adapters that must reconcile two libraries, UI) | small design space, still Sonnet-sized |
| **O / med** — Opus, thinking medium | contract/type design others depend on; scope enforcement; fallback strategy | wrong choices here cascade |
| **O / high** — Opus, thinking high | novel algorithms with no reference implementation: SoA stitcher, confidence + conformal, estimands/amendments | the "risk centre" work in PLAN.md |

Commit message convention: `p<phase>(<scope>): <what>` e.g. `p1(ground): exact-substring quote resolver`.

---

## §M — Model selection: what the evidence actually supports per role

Test applied to every role: *is there task-matched evidence that a small/specialist model
beats the frontier LLM?* If not → frontier LLM.

| Role | Small-model candidate | Evidence vs frontier | Decision |
|---|---|---|---|
| Table **structure** (grid) | MinerU2.5 (1.2B, local pip lib) | **88.2 TEDS vs Gemini-2.5-Pro 85.7, Qwen2.5-VL-72B 82.2** — beats frontier, deterministic output | **Keep.** The one proven specialist. Local library like Docling/PyMuPDF, not an LLM service |
| Table **cell content** | Qwen3-VL-30B | ACL 2025: MLLMs better at cell text — measured on *frontier* MLLMs; no evidence a 30B VLM matches them | **Frontier VLM** (`google/gemini-3.1-pro-preview`), cross-checked by `anthropic/claude-sonnet-4.5` vision |
| Second ensemble member | Llama-3.1-8B (`--slm`) | Cross-family ρ=0.54 vs within 0.77 is about *family diversity*, not size. Our 5/6→6/6 fixture win came from diversity, which a stronger second family also gives, at higher own-accuracy | **Frontier, different family** (`openai/gpt-5.1`). `--slm` flag stays as an opt-in experiment, not the design |
| NLI "does the quote support the value?" | MiniCheck-FT5 | **74.7% ≈ GPT-4 75.3%** — equal, not better; its case was cost | **Frontier, cross-family** from the extractor |
| Entity spotting (drug/lab/visit/AE) | GLiNER-BioMed | 59.8% / 70.4% F1 — good for size; frontier zero-shot biomedical NER is higher. Its case was throughput | **Frontier LLM**, and only as a support signal for completeness accounting |
| Section routing residue | gpt-oss-20b | "structured generation helps classification" — no small-vs-frontier comparison | **Deterministic first** (bookmarks/ToC/headings); frontier LLM for the residue only |
| High-volume narrow fields | QLoRA Llama-8B | 90.0% exact match, non-inferior to a **2nd human** — never compared to a frontier model on the same fields | **Not now.** Revisit after Phase 4 only if a domain's frontier accuracy is below what the tuning paper reports |

Net effect: fewer roles, higher per-call cost, no silent accuracy trade-offs. Cost is
contained by the disk cache (0.3), by verifying only the *uncertain subset*, and by sharding
— not by downgrading models.

## Role → OpenRouter slug (`config/models.yaml`, created in CP0-B)

All slugs verified on the live catalog 2026-09-17. Every role is one line to change.

| Role | Slug | Rule |
|---|---|---|
| `extract` (all domains, text) | `anthropic/claude-sonnet-4.5` | primary extractor |
| `extract_alt` (second ensemble member) | `openai/gpt-5.1` | must differ in family from `extract` |
| `verify` (quote↔value NLI, uncertain subset only) | `google/gemini-3.1-pro-preview` | third family; never the extractor judging itself |
| `vision` (SoA cell content) | `google/gemini-3.1-pro-preview` | frontier VLM |
| `vision_alt` (cell cross-check on grid disagreement) | `anthropic/claude-sonnet-4.5` | different family from `vision` |
| `hard_reasoning` (estimands, amendments, cross-section) | `anthropic/claude-opus-4.8` | escalation tier |
| `route` (untyped-section residue only) | `anthropic/claude-sonnet-4.5` | after deterministic detection |

Non-LLM specialists (local libraries, no gateway): PyMuPDF, Docling, **MinerU2.5**.
Rule carried from DESIGN.md §4: extractor and verifier always different families; logprobs never load-bearing.

---

## Phase 0 — Measure before building (≈3 days)

### CP0-A · **Sonnet / low** — on entry read: `spikes/SPIKE_LOG.md`, `assemble/study.py`, `llm/openrouter.py`, `pyproject.toml`

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 0.1 | Clone `data4knowledge/usdm_data` into `spikes/_work/usdm_data` (gitignored); write `spikes/measure_assembler.py` that loads every study's USDM JSON, runs it through `assemble/study.py` + all three gates, and prints pass-rate + per-rule failure histogram to `spikes/reports/assembler_baseline.json` | `spikes/measure_assembler.py` | none (spike) | `p0(spike): measure usdm4 assembler pass rate on usdm_data corpus` |
| 0.2 | Pin `usdm4==0.29.0` exactly; record SHA `ebf7cdb`, CORE rule-set version and errata revision in a new `PINS.md` table; conformance.md links to it | `pyproject.toml`, `PINS.md`, `docs/conformance.md` | existing suite passes | `p0(pins): pin usdm4 0.29.0 and record the three version pins` |
| 0.3 | LLM disk cache + retries: `llm/cache.py` (sqlite at `data/cache/llm.sqlite`, key = sha256(model, messages, params)); `openrouter.py` uses it, adds exponential-backoff retry on 429/5xx, raises on missing key instead of silent stub when `USDM4_REQUIRE_LLM=1` | `llm/cache.py`, `llm/openrouter.py`, `tests/test_llm_cache.py` | cache hit/miss, retry on 429 (mocked `requests`) | `p0(llm): content-addressed disk cache and retry for OpenRouter` |

### CP0-B · **Haiku / off** — on entry read: `llm/config.py`, `llm/base.py`, `.gitignore`

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 0.4 | `config/models.yaml` with the role table above; `llm/config.py` gains `model_for(role)` (env override `USDM4_MODEL_<ROLE>`); `openrouter.py` resolves by role not `ModelTier`; a startup check fails if `extract`, `extract_alt`, `verify` share a family; `--slm` becomes opt-in experimental (off the default path) | `config/models.yaml`, `llm/config.py`, `llm/openrouter.py`, `tests/test_model_roles.py` | env override wins over yaml; same-family config rejected | `p0(llm): role-based model config with cross-family enforcement` |
| 0.5 | Delete the 7 empty stub packages; add `scripts/guard.py` (fail on empty package, file >400 lines, absolute `C:\`/`/home` paths in src); `.github/workflows/ci.yml` = ruff + guard + pytest on py3.12 | `scripts/guard.py`, `.github/workflows/ci.yml`, deletions | guard runs clean | `p0(ci): guardrails — no empty packages, no >400-line files, no hard-coded paths` |
| 0.6 | `spikes/check_amendment_chain.py`: read title/version/date from the 3 dated PDFs in `../Data/Protocols/`, print whether they share a protocol number → confirms Phase 6's amendment corpus | `spikes/check_amendment_chain.py` | none | `p0(spike): confirm the dated local PDFs form one amendment chain` |
| 0.7 | Rewrite the model tables in `PLAN.md` §4, `DESIGN.md` §4, `architecture.html` (orchestration section) and `docs/development.md` to the §M frontier-only table with the per-role evidence verdicts; `docs/development.md` also covers cache, roles, CI; CHANGELOG | PLAN.md, DESIGN.md, architecture.html, docs | — | `p0(docs): frontier-only model roles — accuracy over cost` |

**Phase 0 exit:** a real assembler pass-rate number is in `spikes/reports/`; `PINS.md` exists; CI green.

---

## Phase 1 — Grounded spine (≈2.5 weeks)

### CP1-A · **Opus / medium** — on entry read: `contracts.py`, `assure/__init__.py`, `extract/soa/grid.py`, `pipeline.py`, DESIGN.md §3 L5–L6

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 1.1 | Redesign contracts everything else depends on: `Method` enum (`DET_TEXT, DET_TABLE, LLM_SMALL, LLM_FRONTIER, VISION, HUMAN`); `Quote(text, page, char_start, char_end, bbox, verify_pass: "exact"\|"normalized"\|"failed")`; `GroundedCandidate(field, value, method, quote, model_id, prompt_hash)`; `Finding(kind, severity, domain, field, message)` for completeness/sanitizer/repair; `AuditRecord` with all Part 11 fields from DESIGN.md L9; `Document` gains `chars: list[CharSpan]` per page. Keep `AssuredField`/`Decision`. | `contracts.py`, `contracts_audit.py` (keep each <400 lines) | type-level tests only | `p1(contracts): grounded candidate, quote, finding and audit record types` |

### CP1-B · **Sonnet / medium** — on entry read: new `contracts.py`, `ingest/pdf.py`, `extract/metadata.py`, `llm/openrouter.py`

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 1.2 | Char-level geometry: `ingest/pdf.py` uses `page.get_text("rawdict")` to build per-page char spans (offset→bbox) alongside blocks; `Document.text_of(page)` returns text whose offsets index `chars` | `ingest/pdf.py`, `ingest/geometry.py`, `tests/test_geometry.py` | offset↔bbox round-trip on fixture PDF | `p1(ingest): character-level geometry from PyMuPDF rawdict` |
| 1.3 | Quote resolver: `ground/quote.py` — pass 1 exact substring per page; pass 2 normalized (whitespace collapse, ligatures fi/fl, soft hyphens, smart quotes); returns `Quote` with bbox = union of char bboxes; failure → `verify_pass="failed"` (hard reject downstream). | `ground/quote.py`, `tests/test_quote_resolver.py` | exact, normalized, multi-line, ligature, not-found, page-boundary cases | `p1(ground): exact-substring quote resolver with normalized fallback` |
| 1.4 | Audit store: `audit/store.py` sqlite (`data/audit/<pdf_sha>.sqlite`), append-only `AuditRecord` rows; `audit/writer.py` called by pipeline per field decision | `audit/store.py`, `audit/writer.py`, `tests/test_audit_store.py` | insert/read, immutability (no UPDATE path) | `p1(audit): append-only Part 11 audit store` |
| 1.5 | Two-pass sharded LLM extraction: `extract/shards.py` defines shards (<40 fields) for C1–C4; `llm/prompts/*.md` versioned (hash into audit); pass 1 free-text reasoning, pass 2 JSON with `{field, value, quote}`; every value must carry a quote. Rewrite `extract_llm` in metadata/design/eligibility/objectives to use shards | `extract/shards.py`, `llm/prompts/`, `llm/two_pass.py`, four extractors, `tests/test_shards.py` | shard sizes, prompt hash stability, JSON parse with stub LLM | `p1(extract): two-pass sharded extraction with mandatory quotes` |
| 1.6 | Uniform assurance: `assure/` takes `GroundedCandidate`s from `extract` **and** `extract_alt` (two frontier families); verifier = quote `verify_pass` + `verify` role (third family) on the uncertain subset only; C2/C3/C4 drop ad-hoc confidence and go through `assure()`; `run_full` writes `review.json` for all domains | `assure/__init__.py`, `assure/verify.py`, `pipeline.py`, `tests/test_assure_uniform.py` | every domain yields `AssuredField`s; failed quote ⇒ BLOCK | `p1(assure): all domains through one grounded assurance path` |

### CP1-C · **Haiku / off**

| # | Task | Files | Commit |
|---|---|---|---|
| 1.7 | CLI: `--require-llm`, `--roles` print; `docs/pipeline.md` + `docs/modules.md` reflect L5/L6; CHANGELOG | `cli.py`, docs | `p1(docs): phase 1 grounding docs and CLI flags` |

**Phase 1 exit (PLAN.md §8.2):** on a real usdm_data PDF, **100% of emitted fields pass quote verification or are BLOCKed**; pydantic gate clean; every field row in `review.json` has page + bbox.

---

## Phase 2 — Multi-page SoA (≈2 weeks) — the risk centre

### CP2-A · **Sonnet / low** — on entry read: `extract/soa/methods.py`, `extract/soa/grid.py`, `pyproject.toml`

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 2.1 | Add `docling` and `mineru` deps (optional extra `[layout]`); `layout/base.py` `TableGrid(page, bbox, cells[row][col] -> CellSpan(text, bbox))`; `layout/docling_adapter.py`, `layout/mineru_adapter.py`; `layout/pymupdf_adapter.py` wraps existing `find_tables` | `layout/*`, `tests/test_layout_adapters.py` | each adapter returns identical dims on the synthetic fixture | `p2(layout): common TableGrid IR with Docling, MinerU and PyMuPDF adapters` |
| 2.2 | Hand-label set: pick 5 multi-page SoAs from usdm_data source PDFs; `data/labels/soa/<nct>.json` (page ranges, expected dims, expected mark matrix) — labels are frozen and versioned | `data/labels/soa/`, `spikes/label_soa.py` helper | — | `p2(labels): five hand-labelled multi-page SoA ground truths` |

### CP2-B · **Opus / high** — on entry read: `layout/base.py`, `extract/soa/grid.py`, the 5 label files, PLAN.md §3 L2

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 2.3 | **Stitcher** `soa/stitch.py`: candidate continuation detection (header-row repeat, column x-alignment within tolerance, "continued"/"cont." markers, same activity-column width, page adjacency); merge rows across pages; detect column drift and split tables; **hard-fail with a `Finding` on ambiguity**, never silently merge. Emits `StitchedGrid` with per-cell page + bbox. | `soa/stitch.py`, `soa/continuation.py`, `tests/test_stitch.py` | 5 labelled SoAs reproduce dims + activity rows; synthetic ambiguous case fails loudly | `p2(soa): multi-page SoA stitcher with loud failure on ambiguity` |

### CP2-C · **Sonnet / medium** — on entry read: `soa/stitch.py`, `extract/soa/crossval.py`, `assemble/soa.py`, `config/models.yaml`

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 2.4 | Grid disagreement signal: run Docling ∥ MinerU on each table region; cell-wise structural agreement becomes a feature on `AssuredCell`; disagreement → that cell goes to the VLM pass | `soa/grid_agreement.py`, `tests/test_grid_agreement.py` | agree/disagree matrix | `p2(soa): Docling/MinerU structural agreement signal` |
| 2.5 | VLM cell-content pass: crop cell/row images via PyMuPDF `clip`, call `vision` role (frontier) for mark/text; `vision_alt` (different family) only on cells where grid text and `vision` disagree; every cell keeps bbox provenance. Replaces the `extract_vision` no-op. | `soa/vision_cells.py`, `extract/soa/methods.py`, `tests/test_vision_cells.py` (stub LLM) | `vision_alt` invoked only on disagreement | `p2(soa): frontier VLM cell-content pass with cross-family check` |
| 2.6 | Mechanical re-derivation (soa2usdm pattern): rebuild mark matrix purely from cell geometry + glyph detection (X/✓/●), compare to LLM/VLM matrix; disagreements → `Finding`s + `corrections.json` sidecar that never overwrites raw extraction | `soa/rederive.py`, `soa/corrections.py`, `tests/test_rederive.py` | ≥95% cell agreement on the 5 labelled SoAs; disagreements listed | `p2(soa): mechanical mark-matrix re-derivation and corrections sidecar` |
| 2.7 | Wire stitched grid into `assemble/soa.py`; `convert-soa` uses new path; docs/CHANGELOG (Haiku-sized, do it here to avoid a switch) | `assemble/soa.py`, `cli.py`, docs | existing SoA tests still pass | `p2(soa): assemble from stitched, re-derived grid` |

**Phase 2 exit (PLAN.md §8.3):** a 5-page SoA stitched, extracted, and independently re-derived; disagreements surfaced not merged.

---

## Phase 3 — Routing, prohibited scopes, completeness (≈2 weeks)

### CP3-A · **Haiku / off** — port only, no tests (your rule). On entry read nothing but the source files.

| # | Task | Source → Dest | Commit |
|---|---|---|---|
| 3.1 | Port `study_adaptation_models.py` near-verbatim (rename module, drop unused imports) | `…/app/services/study_adaptation_models.py` (237) → `sections/models.py` | `p3(port): study fingerprint / route plan dataclasses from reference extractor` |
| 3.2 | Extract the section taxonomy constants (`soa_main`, `soa_followup`, `soa_table_current`, `soa_table_historic`, `amendment_table`, `estimands_table`, `lab_appendix_table`, …) into `config/section_taxonomy.yaml`; extract the 11 protocol families from `study_fingerprint.py` into `config/protocol_families.yaml` | `protocol_section_graph.py` (708), `study_fingerprint.py` (852) → YAML | `p3(port): section taxonomy and protocol families as config data` |
| 3.3 | Copy the domain→route mapping tables from `study_plan_generator.py` and the page-selection heuristics from `hard_page_selector.py` into `sections/_ported_routes.py` / `sections/_ported_pages.py` (marked ported, excluded from coverage) | (916), (503) → `sections/_ported_*.py` | `p3(port): route mapping and page-selection heuristics` |

### CP3-B · **Opus / medium** — on entry read: `sections/models.py`, both YAMLs, `ingest/pdf.py` (bookmarks), `extract/shards.py`, `assure/__init__.py`

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 3.4 | Section graph: deterministic-first detection from PDF bookmarks/ToC + heading blocks → typed sections per taxonomy; `route` role only for untyped residue. Fingerprint from deterministic signals (family YAML) first. Route plan built via ported mapping. | `sections/graph.py`, `sections/fingerprint.py`, `sections/plan.py`, `tests/test_section_graph.py` | our detector on 3 usdm_data PDFs; ported code untested | `p3(sections): deterministic section graph, fingerprint and route plan` |
| 3.5 | Scope enforcement: evidence windows for every shard are filtered by `DomainRoutePlan.prohibited_scopes`; `soa_table_historic` and `amendment_table` never feed current-design shards; audit records log the route plan hash | `extract/windows.py`, `extract/shards.py`, `tests/test_scope_leak.py` | a synthetic protocol with an amendment appendix: old arm count must NOT leak into design | `p3(scope): prohibited-scope filtering of evidence windows` |
| 3.6 | Completeness accounting: `assure/completeness.py` — per-domain expectation rules (visits from design vs SoA columns; arms vs cells; activities vs footnote refs; objectives count vs endpoints) using ideas from `usdm_coverage.py`/`study_validators.py` (ported constants only); mismatch → `Finding(kind="completeness")`, surfaced in `review.json` | `assure/completeness.py`, `tests/test_completeness.py` | each rule fires on a crafted mismatch | `p3(assure): completeness accounting — expected vs found` |

### CP3-C · **Sonnet / low**

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 3.7 | Eval harness skeleton: `eval/corpus.py` (usdm_data loader), `eval/run.py` (routing on/off, writes per-field diff + summary md) ; docs + CHANGELOG | `eval/*`, `tests/test_eval_corpus.py`, docs | loader finds N studies | `p3(eval): routing on/off comparison harness` |

**Phase 3 exit (PLAN.md §8.4):** measured delta with routing on vs off; ≥1 documented leak prevented by `test_scope_leak.py`.

---

## Phase 4 — Confidence + conformal (≈2 weeks)

### CP4-A · **Sonnet / medium** — on entry read: `eval/corpus.py`, `contracts.py`, `assure/__init__.py`

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 4.1 | Ground-truth labels: flatten usdm_data USDM JSON to per-field labels (`data/labels/fields/<nct>.jsonl`, frozen, with `labeler`/`labeled_at`); scorer (exact / normalized / fuzzy per field type); local 4 PDFs held out | `eval/labels.py`, `eval/score.py`, `tests/test_score.py` | scorer on hand cases | `p4(eval): frozen field labels from usdm_data and a typed scorer` |
| 4.2 | Feature extraction per field: quote verify_pass, text-vs-OCR flag, NLI verdict, cross-model agreement (exact+fuzzy), field type, retrieval score, table-cell flag, grid agreement, span length, page position → `features.parquet` | `assure/features.py`, `tests/test_features.py` | feature vector shape/stability | `p4(assure): multi-signal feature extraction` |

### CP4-B · **Opus / high** — on entry read: `assure/features.py`, `eval/score.py`, PLAN.md §2.3, DESIGN.md L6

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 4.3 | Confidence model (logistic / small GBM) + Platt recalibration; **split conformal with SSBC** small-sample correction producing a threshold for `auto_accept` at target α; risk-coverage curve; model + threshold + calibration-set hash saved and logged in audit; guardrails: refuse to emit a bound if n<47 or exchangeability flags (new family) trip | `assure/confidence.py`, `assure/conformal.py`, `tests/test_conformal.py` | synthetic data with known error rate: realized error among accepted ≤ α; n<47 refuses | `p4(assure): calibrated confidence and SSBC-corrected conformal threshold` |

### CP4-C · **Sonnet / low**

| # | Task | Files | Commit |
|---|---|---|---|
| 4.4 | `usdm4 eval` CLI → scoreboard (md + json): auto-accept coverage, review burden, realized error, per-domain; docs + CHANGELOG | `cli.py`, `eval/report.py`, docs | `p4(eval): scoreboard and risk-coverage report` |

**Phase 4 exit (PLAN.md §8.5):** risk-coverage curve published; realized error among auto-accepted ≤ α on held-out PDFs.

---

## Phase 5 — Review UI + certification (≈2 weeks)

### CP5-A · **Sonnet / medium** — on entry read: `audit/store.py`, `pipeline.py` (review.json shape), `ingest/geometry.py`

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 5.1 | FastAPI + Jinja2 + HTMX app (`review/app.py`, templates): list runs; field table sorted by risk; click-to-source renders a PyMuPDF `clip` crop of the quote bbox; edit → new `AuditRecord` (prior value, reason); certify button writes signature-meaning record; localhost only, no auth | `review/*`, `templates/*`, `tests/test_review_api.py` | API: list, crop endpoint returns PNG, edit appends audit row | `p5(review): HTMX review UI with click-to-source crops and audited edits` |
| 5.2 | Post-edit-distance telemetry: per certified run compute normalized edit distance per field; export edits as new labels into `data/labels/edits/` (never overwriting frozen labels) | `review/telemetry.py`, `tests/test_telemetry.py` | distance on hand cases | `p5(review): post-edit distance and edit→label export` |
| 5.3 | `docker-compose.yml` adds `review` service; remove Neo4j service (deferred); docs (`docs/review.md`) + CHANGELOG — Haiku-sized, done here | docker, docs | — | `p5(docs): review UI docs and compose service` |

**Phase 5 exit:** a reviewer certifies one real protocol end-to-end; edits appear as labels.

---

## Phase 6 — Hard domains + repair loop (≈3 weeks)

### CP6-A · **Opus / high** — on entry read: `extract/shards.py`, `sections/plan.py`, `assemble/study.py`, `validate/gate.py`, `spikes/reports/assembler_baseline.json`

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 6.1 | Estimands extractor (sharded, grounded, `hard_reasoning` role, `extract_alt` as second member): population, variable, intercurrent events + strategies, summary measure → usdm4 estimand entities | `extract/estimands.py`, `assemble/estimands.py`, `tests/test_estimands.py` | synthetic estimands section | `p6(estimands): grounded estimand extraction` |
| 6.2 | Amendments: diff the amendment chain (3 dated PDFs from 0.6) — section-level text diff → changed fields → usdm4 amendment entities with rationale quotes | `extract/amendments.py`, `assemble/amendments.py`, `tests/test_amendments.py` | two synthetic versions with a known change | `p6(amendments): amendment-chain diff to USDM amendment entities` |
| 6.3 | Assembler fallback + repair loop: input sanitizer (`assemble/sanitize.py`, repairs → `Finding`s); per-section `usdm4.builder` fallback with **assembler reliance ratio** reported; `validate/repair.py` rule→(domain, field) map, ≤2 bounded re-extraction rounds, unresolved → REVIEW/BLOCK | `assemble/sanitize.py`, `assemble/fallback.py`, `validate/repair.py`, tests | sanitizer repairs emit findings; repair loop terminates | `p6(assemble): sanitizer, builder fallback and bounded repair loop` |

### CP6-B · **Sonnet / medium**

| # | Task | Files | Test | Commit |
|---|---|---|---|---|
| 6.4 | Sites / organizations / roles (weakest published category): sharded extraction + sponsor `StudyRole` emitted via builder fallback | `extract/sites.py`, `assemble/sites.py`, tests | synthetic site list | `p6(sites): organisations, sites and study roles` |
| 6.5 | SoA timing windows + relative anchors + biomedical-concept ids (Bucket 2 of conformance.md) | `soa/timing.py`, `assemble/soa.py`, tests | windows parsed | `p6(soa): timing windows and anchors` |
| 6.6 | Docs, CHANGELOG, conformance.md bucket table refresh — Haiku-sized, done here | docs | — | `p6(docs): hard domains` |

**Phase 6 exit:** amendment chain across the 3 dated versions produces USDM amendment entities; d4k findings in Bucket 1/2 measurably reduced vs Phase 0 baseline.

---

## Phase 7 — Scoreboard (≈1 week)

### CP7 · **Sonnet / low** then **Haiku / off** for 7.2

| # | Task | Files | Commit |
|---|---|---|---|
| 7.1 | `spikes/run_core_corpus.py`: full CORE run (`--core`) over usdm_data + held-out PDFs, pinned rule set/errata; publishes `docs/scoreboard.md` (auto-accept coverage, review burden, realized error, CORE pass rate, assembler reliance ratio) | script, `docs/scoreboard.md` | `p7(eval): full CORE run and published scoreboard` |
| 7.2 | README / index.md / CHANGELOG final; `architecture.html` status line | docs | `p7(docs): v0.3 complete` |

---

## Checkpoint summary (where you switch)

| CP | Model / thinking | Tasks | Rough share of tokens |
|---|---|---|---|
| 0-A | Sonnet / low | 0.1–0.3 | small |
| 0-B | Haiku / off | 0.4–0.7 | tiny |
| 1-A | Opus / medium | 1.1 | small |
| 1-B | Sonnet / medium | 1.2–1.6 | large |
| 1-C | Haiku / off | 1.7 | tiny |
| 2-A | Sonnet / low | 2.1–2.2 | small |
| 2-B | Opus / high | 2.3 | medium |
| 2-C | Sonnet / medium | 2.4–2.7 | large |
| 3-A | Haiku / off | 3.1–3.3 | small |
| 3-B | Opus / medium | 3.4–3.6 | medium |
| 3-C | Sonnet / low | 3.7 | small |
| 4-A | Sonnet / medium | 4.1–4.2 | medium |
| 4-B | Opus / high | 4.3 | medium |
| 4-C | Sonnet / low | 4.4 | small |
| 5-A | Sonnet / medium | 5.1–5.3 | large |
| 6-A | Opus / high | 6.1–6.3 | large |
| 6-B | Sonnet / medium | 6.4–6.6 | medium |
| 7 | Sonnet / low → Haiku / off | 7.1 → 7.2 | small |

18 switches over ~17 weeks; Opus is used in exactly five checkpoints. Within a checkpoint I never switch. At every boundary I will say **"Checkpoint X done — switch to `<model>`, thinking `<level>`, then say go"** and stop.

---

## Verification (end-to-end)

1. `ruff check src tests && python scripts/guard.py && pytest` green at every commit (CI enforces from 0.5).
2. Phase exits above map 1:1 to PLAN.md §8 — each is a command that prints a number or a passing test, not a judgement.
3. Live check before Phase 1: `usdm4 convert-full <usdm_data pdf> --require-llm` with `OPEN_ROUTER_KEY` set; inspect `review.json`: every row has `quote`, `page`, `bbox`, `verify_pass ∈ {exact, normalized}` or `decision == BLOCK`.
4. Cost control: the disk cache (0.3) makes every re-run of the eval free; `usdm4 eval` prints total OpenRouter spend from the cache's usage column.

## §F — Parked: small/self-hosted models (not in this plan)

MiniCheck-FT5, GLiNER-BioMed and a QLoRA-tuned 8B are **not** scheduled. Their published
evidence shows parity or cost advantage, not an accuracy win over frontier models (§M).
They return only if Phase 4's scoreboard shows a specific domain where frontier accuracy
falls below what their papers report — then a tuned model is worth a trial. Because roles
are config (0.4) and the `LLM` protocol in `llm/base.py` already abstracts the caller,
such a trial is one adapter file plus one YAML line — no pipeline change.

Also: PLAN.md §4, DESIGN.md §4, `architecture.html` and `docs/development.md` currently
describe the earlier SLM-tiered table. Task 0.7 rewrites those sections to match §M.
