# DECISIONS (newest first; never delete, mark superseded)
All entries below are inferred from the repo docs on 2026-09-29: inferred - confirm.

- 2026-09-30 | Missing data is left empty and reported, never filled with a plausible value (sentinel `[not extracted]` only where usdm4 requires a non-empty name) | Invented "Phase 1"/criteria were indistinguishable from extracted values | Alt: keep placeholders | C-8
- 2026-09-30 | Geometry SoA reader is delivered; the vision reader is only the fallback when no ruled table exists | Bake-off: geometry 40.3% vs vision 36.2% pooled; vision-only marks 15% correct | Alt: merge both | C-2/C-3
- 2026-09-30 | Compound codes go to usdm4's compound-codes extension, not a second StudyIdentifier | A second sponsor-scoped identifier fails DDF00172 (error) | Alt: sponsor-scoped identifier | C-11
- 2026-09-30 | OCR is not run; scanned PDFs are refused with 422 `scanned_pdf_no_ocr` | Needs a Tesseract dependency, which needs approval | Alt: add OCR now | C-9
- 2026-09-30 | Raw CORE finding counts are not quoted as conformance | Terminology packages are members-only, 1,336 of 1,558 findings are un-judgeable | Alt: report the raw count | C-12
- 2026-09-29 | One plan only: PLAN.md at repo root; old PLAN/DEVPLAN/ROAD_TO_89 archived in docs/ai/archive | Too many overlapping plans inside and outside the repo | Alt: keep several | -
- 2026-09-29 | Review UI is localhost-only with no auth | Part 11 PoC scope (docs/review.md) | Alternatives: add auth | -
- 2026-09-29 | Proprietary license despite GPL-3.0 `usdm4` dependency | Internal use is not distribution (README) | Alt: open-source | -
- 2026-09-29 | Neo4j graph layer deferred | Not needed by any scheduled phase (docker-compose.yml, PLAN.md) | Alt: schedule now | -
- 2026-09-29 | Tests never call a live LLM (USDM4_NO_LLM=1) | Fast, free, deterministic suite | Alt: recorded live calls | -
- 2026-09-29 | Quotes resolved to page/bbox by code, never by the model | Models hallucinate coordinates; grounding must be verifiable | Alt: model-supplied offsets | -
- 2026-09-29 | Logprobs never load-bearing | Not all OpenRouter providers return them (Anthropic doesn't) | Alt: logprob confidence | -
- 2026-09-29 | `usdm4` pinned exactly at 0.29.0 | Conformance results must be reproducible (PINS.md) | Alt: >= floor | -
- 2026-09-29 | OpenRouter default gateway, direct Anthropic fallback, stub last | Multi-model ensembles behind one key (llm/router.py) | Alt: single provider | -
- 2026-09-29 | Frontier LLMs by default; SLMs parked (--slm) | Published evidence favors frontier models (PLAN.md 4.2); accuracy over cost | Alt: small models for cost | -
