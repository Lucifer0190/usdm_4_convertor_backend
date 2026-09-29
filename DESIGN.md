# Protocol → USDM 4.0 Conversion System — Technical Design (v0.3)

**Codename:** USDM4-Assure
**Status:** architecture revised against published evidence; build in progress
**Author:** Kirtikumar (Hexaware HTL) + Claude
**Date:** 2026-09-16 · *(v0.2: 2026-08-14)*
**Companion:** [`docs/ai/archive/PLAN-v0.3-evidence-and-roadmap.md`](docs/ai/archive/PLAN-v0.3-evidence-and-roadmap.md) (evidence + roadmap) · [`docs/`](docs/index.md) (reference)

> **What changed in v0.3.** v0.2 was built on two numbers and one piece of arithmetic that
> did not survive a literature review: a "~89% field / ~76% SoA market ceiling," and the
> claim that two independent paths yield ~97–99% precision on their agreed set. Both are
> corrected below. The *layered* architecture and the human-in-the-loop accuracy contract
> survive intact; the mechanisms inside the layers change substantially. Full citations in
> [`docs/ai/archive/PLAN-v0.3-evidence-and-roadmap.md`](docs/ai/archive/PLAN-v0.3-evidence-and-roadmap.md).

---

## 0. The thesis — what actually beats the state of the art

### 0.1 What the published evidence says

| Finding | Source |
|---|---|
| Best published accuracy on protocol → structured fields: **89.0%** (best-in-class RAG + frontier model). ~1 field in 9 is wrong | [Babaeipour et al. 2026](https://arxiv.org/abs/2602.00052) |
| On ~358-page documents, frontier models retain only **48–53% recall** — *at high precision* | [LongExtractionBench](https://www.micro1.ai/benchmark/long-extraction) |
| **0% valid output** from every frontier model on a 369-field schema | [ExtractBench](https://arxiv.org/abs/2602.12247) |
| Cross-model error correlation **ρ = 0.74–0.82**; **48%** of mistakes replicate across model families | [Oracle's Fingerprint](https://arxiv.org/pdf/2605.00844) |
| A **1.2B** specialist table model beats Gemini-2.5-Pro and a 72B VLM on table structure (88.2 vs 85.7 vs 82.2 TEDS) | [MinerU2.5](https://arxiv.org/html/2509.22186v1) |
| Verbatim-grounded extraction: **93.0% vs 19.0%** exact match | [CogCanvas](https://arxiv.org/html/2601.00821v2) |
| Fused multi-signal confidence: **0.928 AUC** vs logprobs 0.705, verbalized 0.692, self-consistency 0.744 | [ExtractConf](https://arxiv.org/pdf/2606.24420) |

### 0.2 The real failure mode

**Silent omission, not incorrect values.** Systems return a confident, well-formed,
schema-valid study that is quietly *missing* rows, visits, criteria and arms. Nothing
looks broken. In a regulated workflow this is the worst possible failure.

Every mechanism below is chosen to attack that specific failure:

| # | Failure | Counter-mechanism | Where |
|---|---|---|---|
| 1 | **Silent omission under long context / wide schema** | **Sharded extraction** (<40 fields/call, ≤5 nesting levels) over **routed evidence windows** + **completeness accounting** (expected vs found) | §3 L3–L4, L6 |
| 2 | **Ungrounded values** — a plausible value with no real source | **Mandatory verbatim quote**, resolved to page + char offset + bbox **by our code, not the model**; exact-substring mismatch is a hard reject | §3 L5 |
| 3 | **Table structure destroyed** — merged cells, multilevel headers, tables spanning 3–6 pages | **Specialist model owns the grid, VLM owns the cell content**; plus a **custom multi-page stitcher**, because no available tool solves this | §3 L1–L2 |
| 4 | **Dishonest confidence** — reviewers can't tell which fields are risky | **Multi-signal calibrated confidence** (grounding features first) + **conformal bound** on the auto-accepted set | §3 L6 |

### 0.3 The accuracy claim we can actually defend

v0.2 claimed: *two paths at ~89% ⇒ ~97–99% precision on the agreed set.* **This is not
supportable.** It assumes independent errors; measured correlation is ρ = 0.74–0.82, and
errors originating in a shared parsing stage are ρ = 1.0 across every downstream model.
Unanimous agreement on a *wrong* answer is common, and systematically so on exactly the
hard fields we care about.

What we claim instead:

> **Every field carries a verifiable verbatim citation to page and coordinates, a
> calibrated confidence, and a statistically-bounded auto-accept decision — with a Part 11
> audit trail and measurably less reviewer time.**

Ensemble agreement remains valuable — as **one feature in a calibrated confidence model**,
never as a precision guarantee.

---

## 1. The accuracy contract (unchanged — and now better supported)

"100% accuracy for clinical use" is a **human-in-the-loop certification guarantee**, not
zero-touch output. The system's job is to (a) maximise un-reviewed accuracy, (b) make
confidence trustworthy so review is surgical, and (c) block non-conformant output at the
conformance gate.

The published evidence *strengthens* this position: at 89% SOTA, human review is not
optional, so the product's real job is to make review **efficient and auditable** rather
than to eliminate it. A 13-coordinator study found this class of tool cut processing time
**40%** with higher rated quality — that is the win, and it is measurable.

---

## 2. Build strategy — assemble on the ecosystem

**Decision: build on the `data4knowledge` `usdm4` package, and treat its ground-truth
corpus as our eval seed.**

- **`usdm4`** gives the pydantic USDM 4.0 model, the `Assembler` / `TimelineAssembler`, a
  bundled d4k rule library, an offline controlled-terminology cache, and a CORE facade.
  Rebuilding this is what sank comparable projects.
- **`data4knowledge/usdm_data`** has **~20 real studies** mapped to USDM and CORE-validated,
  each traceable to a public NCT protocol PDF. **This is our ground-truth seed** — it
  replaces the plan to hand-label four local PDFs from scratch, which become a held-out set.
- **`kerfors/soa2usdm`** (MIT, PHUSE 2025) is a permissively-licensed reference for the SoA
  path; its **mechanical re-derivation of the mark matrix** pattern is adopted directly.

Three constraints to record rather than discover later:

1. **`usdm4` is GPL-3.0.** Internal use is not distribution, so this is workable — but it
   must be a recorded decision, not an accident.
2. **Pin three versions independently:** USDM model version, CORE rule-set version, and
   errata revision. USDM v4.0 shipped June 2025; executable CORE rules only appeared in
   December 2025; **27 errata** already exist, some flipping ERROR↔WARNING. Treat rule
   severity as data.
3. **The upstream assembler is the integration risk.** Its own corpus run showed
   assembly failures on real protocols. The currently vendored source is *newer than PyPI*
   and already fixes two bugs its docs list as open — so **re-measure before designing
   around it** (Phase 0), and keep a per-section fallback to `usdm4.builder`.

---

## 3. Layered architecture

```
┌─ L0 · SUBSTRATE ────────────────────────────────────────────┐
│ PyMuPDF: text layer, character bboxes, bookmarks/ToC         │ deterministic
│ → character-level provenance for free. Never OCR born-digital│
└──────────────────────────────────────────────────────────────┘
┌─ L1 · LAYOUT & TABLES ──────────────────────────────────────┐
│ Docling (layout, reading order) ∥ MinerU2.5 (table grids)     │ two engines
│ → their disagreement is the cheapest quality signal we get    │
└──────────────────────────────────────────────────────────────┘
┌─ L2 · ★ MULTI-PAGE SoA STITCHER (custom) ───────────────────┐
│ header-signature matching · "(continued)" cues · column       │ THE RISK CENTRE
│ reconciliation · hard-fail loudly, never silently split       │
└──────────────────────────────────────────────────────────────┘
┌─ L3 · ROUTING ──────────────────────────────────────────────┐
│ section graph · study fingerprint · extraction plan           │
│ primary / supporting / PROHIBITED scopes, 4-axis scoping      │
└──────────────────────────────────────────────────────────────┘
┌─ L4 · EXTRACTION ───────────────────────────────────────────┐
│ sharded: <40 fields/call, ≤5 nesting, narrow evidence windows │
│ two-pass: free-text reasoning → constrained JSON emission     │
└──────────────────────────────────────────────────────────────┘
┌─ L5 · ★ GROUNDING ──────────────────────────────────────────┐
│ model emits a VERBATIM QUOTE; our code resolves page+char+bbox│ hard gate
│ exact-substring mismatch → reject. Model never emits coords.  │
└──────────────────────────────────────────────────────────────┘
┌─ L6 · ★ ASSURANCE ──────────────────────────────────────────┐
│ multi-signal confidence → conformal threshold → triage        │ the moat
│ + COMPLETENESS accounting (expected vs found)                 │
└──────────────────────────────────────────────────────────────┘
┌─ L7 · ASSEMBLY ─────────────────────────────────────────────┐
│ input sanitizer → usdm4 Assembler → per-section builder       │
│ fallback; report the assembler reliance ratio per run         │
└──────────────────────────────────────────────────────────────┘
┌─ L8 · VALIDATION ───────────────────────────────────────────┐
│ pydantic → d4k rules → CDISC CORE · rule→repair map           │
│ bounded repair loop (≤2 rounds), then hand to review          │
└──────────────────────────────────────────────────────────────┘
┌─ L9 · CERTIFICATION ────────────────────────────────────────┐
│ review UI (click-to-source) · SME sign-off · Part 11 audit    │ the "100%"
└──────────────────────────────────────────────────────────────┘
```

**Governing principle:** *no single model ever owns both the grid and the content of a
table, and no single call ever owns more than ~40 schema fields.*

### L0–L1 · Substrate, layout, tables

Protocols are born-digital, so PyMuPDF's text layer and **character geometry** are exact
and free — and they are what makes L5's quote→coordinate resolution possible. Docling
(MIT) handles layout and reading order; MinerU2.5 handles table grids. Running both on
table regions costs little and yields a disagreement signal that feeds L6.

**Rejected on evidence:** Marker (65.8 table TEDS on the neutral benchmark despite strong
vendor numbers), SmolDocling for tables (0.52 TEDS vs TableFormer's 0.89), standalone TATR
(~75–81% exact match at best, and poorly calibrated off-domain).

### L2 · ★ Multi-page SoA stitcher — the risk centre

**No available tool solves this, and clinical SoA tables routinely span 3–6 pages.**
Docling does not merge cross-page tables (issue #2976, open); MinerU merges but drops
content on continuation pages (#4311, open).

We build it: match column-header signatures across consecutive pages, detect "(continued)"
cues and repeated header rows, reconcile column counts, and **hard-fail loudly** rather
than silently emitting two tables. Gated by a hand-labelled set of 30–50 real multi-page
SoAs.

### L3 · Routing, fingerprinting, prohibited scopes

Evidence: retrieval with chunk provenance beat whole-document stuffing by **26 points**
(89.0% vs 62.6%) — routing is an *accuracy* mechanism, not just a cost optimisation.

- **Section graph** — typed sections with authority surfaces and a `current` vs `historic`
  distinction.
- **Study fingerprint** — classify the protocol family first (11 families as config data),
  then adapt routing, prompts and expectations.
- **Prohibited scopes** — an explicit deny-list per domain, so amendment-history text
  cannot leak into "current design" and an appendix sub-study cannot pollute the main
  schedule. Scoping is 4-axis: study / phase / arm / region.

### L4 · Sharded extraction

Schemas are split into sub-schemas of **<40 fields, ≤5 nesting levels** — forced by
ExtractBench's 0%-at-369-fields result and by structured-output nesting caps. Each call
sees a **narrow, routed evidence window**, never the whole document.

**Two-pass emission everywhere:** free-text reasoning first, constrained JSON second. This
is the practical resolution of the "format restrictions hurt reasoning" debate, and it
costs almost nothing.

### L5 · ★ Grounding — the highest-leverage mechanism

Every field arrives with a **verbatim quote**. Our code locates it by deterministic
substring search (with a whitespace/ligature-normalised second pass; which pass succeeded
becomes a confidence feature). **A failed match is a hard, non-probabilistic reject.**

**The model never emits coordinates** — it emits a quote, and we resolve page, character
offset and bounding box from the PDF's own geometry. Model-emitted coordinates are
hallucination-prone and unsupported by any benchmark.

This is also the **GAMP 5 argument**: deterministic code can be validated classically,
LLM output cannot, so we push as much logic as possible into deterministic checks.

### L6 · ★ Assurance — the moat

**Multi-signal confidence.** Not a hand-tuned formula. Features, in rough order of
published importance: quote-verification outcome (and which normalisation pass), text-layer
vs OCR provenance, NLI entailment score, cross-model agreement (exact + fuzzy), field type,
retrieval score, table-cell flag, span length, page position. Fit a small model; recalibrate
post-hoc (Platt/Lasso works from ~165 samples; isotonic needs ~1000).

> **Logprobs are not load-bearing.** Anthropic exposes none, and OpenRouter's `logprobs`
> parameter is not honoured by every provider — a logprob-dependent design breaks
> *silently* on a model swap.

**Conformal bound.** Split conformal with small-sample (SSBC) correction gives: *under
exchangeability, the expected proportion of incorrect fields among auto-accepted ones is
≤ α*, usable from n ≈ 47. **Say exactly that and no more** — the guarantee is **marginal,
not per-field-type**, and exchangeability breaks on new sponsor templates or therapeutic
areas. Global bound first; per-class only at ~20+ protocols.

**Completeness accounting.** Each domain declares expectations (visit count from design vs
columns in the stitched SoA; arm count vs cells; activity rows vs footnote references). A
mismatch is a **first-class finding** — this is the defence against silent omission.

**Triage.** `auto_accept | review | block`. `block` means "no defensible value; a human must
supply it." Every run reports two numbers: **auto-accept coverage** and **review burden**.

### L7–L8 · Assembly and validation

An **input sanitizer** enforces the assembler's implicit contract before `execute()` — no
empty required strings, valid org-role keys, well-formed enrollment blocks, SoA emitted as
a list of timelines. Sanitizer repairs are surfaced as quality findings ("we had to repair
our own input"), which is a direct extraction-quality signal.

Sections the assembler cannot express (narrative content, scheduled-instance/condition/
transition-rule mechanics, governance dates, abbreviations) go straight to
`usdm4.builder`. Everything else tries the Assembler with an automatic per-section
fallback, and the run reports an **assembler reliance ratio**.

Validation runs three gates — pydantic → d4k rules → CDISC CORE — plus a **rule → repair
action** map that neither prior codebase built. The repair loop is bounded (≤2 rounds,
token/time ceilings): findings map to `(domain, field)`, only those slices are re-extracted
(usually escalating to the vision path), then re-sanitised, re-assembled, re-gated.
Anything unresolved becomes `review`/`block` — never silently dropped.

### L9 · Certification

Every field shows value, source (page/bbox **crop**), method, calibrated confidence,
verifier verdict and conformance status, sorted by risk. SME edits write to the model;
edit history is the audit trail.

**Part 11 audit record, per field, from day one:** model ID + version, prompt hash,
temperature/seed, retrieval config, source PDF SHA-256, page/span/bbox, quote, verification
outcomes, confidence, threshold, decision, reviewer identity, UTC timestamp, prior value,
reason-for-change, signature meaning. *Cheap to design in; brutal to retrofit.*
[ICH E6(R3)](https://www.ct-toolkit.ac.uk/news/summary-key-changes-ich-e6-r3-guidelines)
makes traceability an explicit obligation, so L5 + L9 are closer to compliance requirements
than differentiators.

**Post-edit distance** is captured as the ongoing quality metric — objective, cheap, and it
accumulates labels automatically.

---

## 4. Model orchestration — Frontier LLMs + MinerU2.5

All traffic runs through **OpenRouter** behind `llm/router.py`, with roles declared in
`config/models.yaml` so any model is swappable per role without code changes. Already
implemented: `llm/openrouter.py`, `llm/config.py`, and role-based routing.

**Strategy: accuracy first.** Frontier models (Claude Sonnet 5.5 / Opus 5.5, GPT-6 Sol, Gemini 3.1 Pro)
are the default for all roles. Small models (Llama-3.1-8B, Qwen, gpt-oss-20b) are not in the
design — the published evidence shows frontier models outperform them in every measured
domain. **The one specialist that survives:** MinerU2.5 (1.2B) beats Gemini-2.5-Pro on
table structure extraction (88.2 TEDS vs 85.7).

**What OpenRouter is, precisely.** It proxies providers' hosted chat-completion APIs. It
does not host task-specific NER/NLI encoders (no chat endpoint exists for them to serve),
and it does not accept caller-uploaded fine-tuned checkpoints. Confirmed against the live
catalog (`GET /api/v1/models`, 444 entries, checked 2026-09-17): `GLiNER-BioMed` and
`MiniCheck-FT5` are not there, and were never going to be. Task-specific encoders run
locally (CPU-viable for both) if needed; they are not behind OpenRouter.

| Tier | Component | Job | Model(s) | Notes |
|---|---|---|---|---|
| Deterministic (local) | PyMuPDF · Docling · **MinerU2.5** | text layer, layout, table grids, stitching | n/a — local libraries | 1.2B specialist beats Gemini on TEDS |
| Extract (primary) | LLM C1–C4 all-domain text | `anthropic/claude-sonnet-5.5` | Frontier default | verified live 2026-09-29 |
| Extract (cross-family) | LLM C1–C4 ensemble member | `openai/gpt-6-sol` | Different family from extract | cross-family ρ=0.54; new-family signal needed |
| Verify (NLI) | LLM quote↔value checking | `google/gemini-3.1-pro-preview` | Third family; never extractor judging itself | frontier NLI accuracy unmeasured vs Llama/Qwen |
| Vision (cell content) | VLM SoA cell text, first pass | `google/gemini-3.1-pro-preview` | Frontier VLM | no evidence 30B VLMs match frontier |
| Vision (cross-check) | VLM cell cross-family signal | `anthropic/claude-sonnet-5.5` | Different family from vision | cross-family diversity needed |
| Hard reasoning | LLM estimands, amendments, cross-section | `anthropic/claude-opus-5.5` | Escalation tier | hardest reasoning tier |
| Section routing (residue) | LLM untyped-section fallback | `anthropic/claude-sonnet-5.5` | After deterministic detection | only residue after bookmarks/ToC/headings |

**Rules.**
- **Cross-family verification only** (ρ = 0.54 cross vs 0.77 within), and **verify only the
  uncertain subset** to control cost.
- **Never let the extracting model judge its own output** — self-preference bias up to +90%.
- **If sampling for self-consistency, sample in YAML/free-text and vote, then emit JSON
  once** — JSON-constrained decoding collapses answer diversity (modal share 41% → 64%), so
  voting under a JSON grammar is far less independent than it appears.
- **Do not build:** verbalized confidence as a gate (0.692 AUC — worse than logprobs);
  SmolDocling anywhere near tables; model-emitted coordinates.
- All prompts version-controlled and hashed into the audit trail; a prompt change is a
  potential accuracy regression and re-runs the eval.

---

## 5. Eval & calibration — measure, then claim

**Ground truth.** Seed from `data4knowledge/usdm_data` (~20 studies, CORE-validated, public
source PDFs). Our four local PDFs are **held out**. Labels are versioned, carry
`labeler`/`labeled_at`, and are **frozen** — when the pipeline disagrees with truth we fix
the pipeline or file a justified truth correction, never silently edit truth.

**Metrics.**
- **Field-level** accuracy, reported both at 100% coverage *and* on the auto-accept subset
  (the number that matters operationally).
- **SoA** cell-level P/R/F1 plus structural exact-match (visit/activity/epoch counts). Note
  the honest comparison: Kramer/MITRE's 76% is a **whole-SoA pass rate** (22/29), a stricter
  bar than per-cell accuracy — beating it means 23+/29 *fully correct* timelines.
- **Conformance:** d4k and CORE finding counts, plus the assembler reliance ratio.
- **Operational:** review burden, median certification time, post-edit distance.
- **Headline calibration metric is Brier score** (strictly proper), with CORP reliability
  diagrams for the visual. ECE only as a secondary, with bin count pre-registered — it is
  binning-sensitive and not a proper scoring rule.
- **Risk-coverage (AURC)** is the deployment-facing metric: "auto-accept X% of fields at
  ≤Y% error; review the rest."

**Calibration.** Fit on pooled `(confidence, correct)` pairs with **leave-one-protocol-out**
CV. Note that 4 protocols ≈ 1,200 field-level labels — enough for global recalibration and
an SSBC-corrected global conformal bound, **not** enough for per-field-type guarantees.
State that asymmetry explicitly in anything shown to a sponsor.

**Discipline:** accuracy is *reported* by the eval command, never asserted in a unit test.
Test correctness; measure accuracy.

---

## 6. Repository layout

```
usdm4_assure/
  ingest/        L0 — pdf → text layer, char bboxes, page images
  layout/        L1 — Docling / MinerU adapters, table regions
  soa/           L2 — multi-page stitcher (★ risk centre), grid reconciliation
  sections/      L3 — section graph, fingerprint, route plan, prohibited scopes
  extract/       L4 — sharded domain extractors
  ground/        L5 — quote → page/char/bbox resolution, exact-substring gate
  assure/        L6 — ★ confidence features, calibration, conformal, completeness, triage
  assemble/      L7 — sanitizer, Assembler adapter, builder-direct fallback, strategy
  validate/      L8 — three gates, rule→repair map, bounded repair loop
  review/        L9 — review UI, sign-off, Part 11 audit trail
  llm/           OpenRouter router, provider adapters, versioned prompts, disk cache
  eval/          ground truth, scoring, calibration, scoreboard
  tests/
  docker/
```

*Stub packages are not created ahead of their code* — v0.2 left seven empty 1-line packages
that made the design look implemented when it was not. CI now fails on empty packages,
files over 400 lines, hard-coded machine paths, and any field lacking evidence.

---

## 7. Phased plan

Detail and exit criteria in [`docs/ai/archive/PLAN-v0.3-evidence-and-roadmap.md` §6](docs/ai/archive/PLAN-v0.3-evidence-and-roadmap.md). Summary:

| Phase | Deliverable |
|---|---|
| **0** (3d) | Re-measure the assembler on current `usdm4`; pull the ~20-study corpus; CI guardrails |
| **1** (2.5wk) | Substrate + **grounding** + Part 11 audit + backbone domains + three gates, on a **real** protocol |
| **2** (2wk) | **Multi-page SoA stitcher** + dual-engine grid + VLM cell pass + mechanical re-derivation |
| **3** (2wk) | Fingerprint, section graph, prohibited scopes, completeness accounting |
| **4** (2wk) | Multi-signal confidence + recalibration + conformal; first honest scoreboard |
| **5** (2wk) | Review UI, certification, post-edit-distance telemetry |
| **6** (3wk) | Estimands, amendments, sites (weakest published category), then the hardest tier |
| **7** (1wk+) | Full CORE run on real protocols; publish a reproducible number |

---

## 8. Decisions on record

- ✅ Python 3.12 single pin (the CDISC stack has no 3.13 wheel).
- ✅ Build on `data4knowledge/usdm4`; **do not** reimplement the USDM class hierarchy.
- ✅ `usdm4` is **GPL-3.0** — acceptable for internal use (not distribution), recorded deliberately.
- ✅ **OpenRouter** as the gateway, multi-model by role, SLM-tiered where proven.
- ✅ Ground truth seeded from `usdm_data`; the four local protocol PDFs are held out.
- ✅ Logprobs never load-bearing; verbalized confidence never a gate.
- ✅ Human certification of every field — which is also the argument that this is an
  *operational-efficiency* tool under the FDA framework. **Route the Context-of-Use
  determination through regulatory affairs; do not self-certify it.**
- ⏸️ Deferred deliberately: Neo4j graph store, Merkle/replay receipts, multi-tenant
  SaaS/RBAC, cross-document contradiction detection, SLM fine-tuning (needs the correction
  flywheel first).

---

## 9. Next step — Phase 0, and why it is first

Before any architecture is frozen, **re-measure the foundation**. The "0 of 235 protocols
assembled" figure that shaped our risk posture is **stale**: the vendored `usdm4` source
(v0.29.0) already contains fixes for two of the bugs its own findings doc lists as open.
We therefore do not currently know the real assembler pass rate — and how much we lean on
the Assembler versus `usdm4.builder` depends entirely on that number.

Phase 0 costs days, not weeks:

1. Re-run the assembler over the corpus on the current pinned SHA; publish the pass rate
   and the top three remaining failure modes.
2. Pull `data4knowledge/usdm_data` and confirm how many studies give us usable
   (PDF → USDM) eval pairs.
3. Confirm whether the three dated `Clinical Protocol - 0 (*).pdf` files are versions of one
   study — if so, that is a free amendment-chain fixture and the eval set is "2 studies /
   4 documents," which changes how we talk about generalisation.
4. Stand up CI with the sprawl guardrails.

**Green light from Phase 0 = the design rests on measured reality rather than on a number
nobody has re-checked.**

---

## Sources

Full citation list in [`docs/ai/archive/PLAN-v0.3-evidence-and-roadmap.md`](docs/ai/archive/PLAN-v0.3-evidence-and-roadmap.md). Primary:
Babaeipour et al. 2026 ([arXiv 2602.00052](https://arxiv.org/abs/2602.00052)) ·
Kramer/MITRE ProtocolMiner ([MRA 14(3)](https://esmed.org/MRA/mra/article/view/7362)) ·
[ExtractBench](https://arxiv.org/abs/2602.12247) ·
[LongExtractionBench](https://www.micro1.ai/benchmark/long-extraction) ·
[MinerU2.5](https://arxiv.org/html/2509.22186v1) ·
[ExtractConf](https://arxiv.org/pdf/2606.24420) ·
[Conformal factuality (ICML 2024)](https://proceedings.mlr.press/v235/mohri24a.html) ·
[MiniCheck](https://arxiv.org/abs/2404.10774) ·
[GLiNER-BioMed](https://academic.oup.com/bioinformatics/article/42/6/btag322/8690923) ·
CDISC [DDF-RA](https://github.com/cdisc-org/DDF-RA) / [CORE](https://www.cdisc.org/core) ·
[usdm4](https://github.com/data4knowledge/usdm4) · [usdm_data](https://github.com/data4knowledge/usdm_data) ·
[soa2usdm](https://github.com/kerfors/soa2usdm)
