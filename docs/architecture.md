# Architecture

USDM4-Assure is organized as ten layers (v0.3). Data flows top to bottom; each layer
speaks only in the shared contracts from `usdm4_assure.contracts`, which is what lets the
Assurance layer treat any extractor's output uniformly. Full evidence and rationale in
[`docs/ai/archive/PLAN-v0.3-evidence-and-roadmap.md`](docs/ai/archive/PLAN-v0.3-evidence-and-roadmap.md) and [`../DESIGN.md`](../DESIGN.md).

```
┌─ L0 · SUBSTRATE ────────────────────────────────────────────┐
│ PyMuPDF: text layer, character bboxes, bookmarks/ToC          │  deterministic
└──────────────────────────────────────────────────────────────┘
┌─ L1 · LAYOUT & TABLES ──────────────────────────────────────┐
│ Docling (layout, reading order) ∥ MinerU2.5 (table grids)     │  two engines
└──────────────────────────────────────────────────────────────┘
┌─ L2 · ★ MULTI-PAGE SoA STITCHER (custom) ───────────────────┐
│ header-signature matching, cross-page reconciliation          │  the risk centre
└──────────────────────────────────────────────────────────────┘
┌─ L3 · ROUTING ──────────────────────────────────────────────┐
│ section graph · study fingerprint · prohibited scopes          │
└──────────────────────────────────────────────────────────────┘
┌─ L4 · EXTRACTION ───────────────────────────────────────────┐
│ sharded (<40 fields/call), narrow evidence windows             │
└──────────────────────────────────────────────────────────────┘
┌─ L5 · ★ GROUNDING ──────────────────────────────────────────┐
│ verbatim quote → code resolves page/char/bbox → hard gate      │
└──────────────────────────────────────────────────────────────┘
┌─ L6 · ★ ASSURANCE ──────────────────────────────────────────┐
│ multi-signal confidence → conformal threshold → triage         │  the moat
└──────────────────────────────────────────────────────────────┘
┌─ L7 · ASSEMBLY ─────────────────────────────────────────────┐
│ sanitizer → usdm4 Assembler → per-section builder fallback     │
└──────────────────────────────────────────────────────────────┘
┌─ L8 · VALIDATION ───────────────────────────────────────────┐
│ pydantic → d4k rules → CORE · rule→repair map · bounded repair │
└──────────────────────────────────────────────────────────────┘
┌─ L9 · CERTIFICATION ────────────────────────────────────────┐
│ review UI · SME sign-off · Part 11 audit trail                 │  the "100%"
└──────────────────────────────────────────────────────────────┘
```

## Why this shape (evidence, not intuition)

Published SOTA on protocol → USDM extraction plateaus around 89% field-level accuracy,
and the dominant failure on long documents is **silent omission at high precision** — a
system that looks confident and complete while quietly missing rows, visits or criteria
([LongExtractionBench](https://www.micro1.ai/benchmark/long-extraction),
[ExtractBench](https://arxiv.org/abs/2602.12247)). Every mechanism below targets that
failure mode specifically.

### 1. No single model owns both a table's grid and its content

A specialist table model (MinerU2.5, 1.2B) beats frontier vision-LLMs on table *structure*
(88.2 vs 85.7 TEDS against Gemini-2.5-Pro), while vision-LLMs are stronger on *cell text*
([MinerU2.5](https://arxiv.org/html/2509.22186v1), ACL 2025 xllm-1.2). L1 splits the job
accordingly: specialist owns the grid, a vision-LLM fills cell content against that fixed
grid.

### 2. Multi-page tables get a dedicated, custom layer

No available tool solves cross-page table continuation correctly — Docling does not merge
across pages (open issue), MinerU merges but drops content on continuation pages (open
bug). Clinical Schedule-of-Activities tables routinely span 3–6 pages, so **L2 is a
purpose-built stitcher**, not a library call, gated against a hand-labelled set of real
multi-page SoAs.

### 3. Routing and scope discipline, not whole-document stuffing

Retrieval with chunk-level provenance beat whole-document context by **26 accuracy
points** in the best published comparison. L3 classifies the protocol's family first (11
documented families), builds a typed section graph, and enforces **prohibited scopes** so
amendment-history text cannot leak into "current design" and an appendix sub-study cannot
pollute the main schedule.

### 4. Sharded extraction, two-pass emission

Wide schemas fail outright — one benchmark measured **0% valid output** at 369 fields.
L4 shards every call to under ~40 fields and ≤5 nesting levels, over a narrow, routed
evidence window. Every call reasons in free text first, then emits constrained JSON —
resolving the published tension between format constraints and reasoning quality at
near-zero cost.

### 5. Grounding is mandatory, and coordinates are never model output

Every field arrives with a **verbatim quote**; our code — never the model — resolves it to
a page, character offset and bounding box using the PDF's own character geometry
(`ingest/` in L0). A failed exact-substring match is a hard reject. Published verbatim
grounding lifts exact-match correctness from 19% to 93%
([CogCanvas](https://arxiv.org/html/2601.00821v2)). This is also the layer that makes the
system classically validatable under GAMP 5: deterministic string matching, not model
judgment.

### 6. Confidence is a fitted model, not a formula — and it is bounded, not just scored

`assure/` fuses grounding-quality features (quote-verification outcome, text-layer vs OCR
provenance, entailment score) with cross-model agreement, field type, and retrieval score
into a calibrated confidence — published fused models reach **0.928 AUC** versus 0.705 for
logprobs alone ([ExtractConf](https://arxiv.org/pdf/2606.24420)). On top of calibration, a
**conformal threshold** gives a provable, if marginal, bound on the error rate among
auto-accepted fields. **Ensemble agreement is one input feature here — not a precision
guarantee.** Measured cross-model error correlation is 0.74–0.82
([Oracle's Fingerprint](https://arxiv.org/pdf/2605.00844)), so "two paths agree ⇒ ~99%
precision" does not hold and is not claimed.

### 7. Completeness accounting defends against silent omission directly

Each domain declares what it expects (visit count from design vs SoA columns; arm count vs
cells) and reconciles against what was actually extracted. A mismatch is a first-class
finding, not a silent pass — this is the direct countermeasure to the dominant failure mode
identified in §0.

## Assemble on the ecosystem, don't reinvent it

USDM4-Assure builds the USDM entities through the **data4knowledge `usdm4`** package
(`assemble/`), which provides:

- the pydantic USDM 4.0 model (structural validation for free),
- the `Assembler` / `TimelineAssembler`, which mint conformant entities and resolve CDISC
  codes offline via a bundled controlled-terminology cache,
- the d4k rule engine and a wrapper around the official CDISC CORE engine (`validate/`).

`usdm4` is GPL-3.0 — acceptable for internal use (not distribution) and recorded as a
deliberate decision, not an oversight. Because the upstream Assembler's own corpus testing
has shown real assembly failures, L7 wraps it with an input sanitizer and a per-section
fallback to `usdm4.builder`, and every run reports an **assembler reliance ratio** rather
than assuming the Assembler will simply work.

Our own value is the **Grounding and Assurance layers** and the domain **extractors** — the
parts that turn a PDF into structured, cited, scored candidates. The
[Conformance](conformance.md) page covers where the upstream assembler's current limits
become ours.

## The shared contracts

Everything between layers is one of a small set of dataclasses in
`usdm4_assure.contracts` (plus the SoA grid types in `extract/soa/grid.py`). See
[Pipeline & contracts](pipeline.md).
