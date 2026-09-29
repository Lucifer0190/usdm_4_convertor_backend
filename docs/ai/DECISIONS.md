# DECISIONS (newest first; never delete, mark superseded)
All entries below are inferred from the repo docs on 2026-09-29: inferred - confirm.

- 2026-09-29 | Review UI is localhost-only with no auth | Part 11 PoC scope (docs/review.md) | Alternatives: add auth | -
- 2026-09-29 | Proprietary license despite GPL-3.0 `usdm4` dependency | Internal use is not distribution (README) | Alt: open-source | -
- 2026-09-29 | Neo4j graph layer deferred | Not needed by any scheduled phase (docker-compose.yml, PLAN.md) | Alt: schedule now | -
- 2026-09-29 | Tests never call a live LLM (USDM4_NO_LLM=1) | Fast, free, deterministic suite | Alt: recorded live calls | -
- 2026-09-29 | Quotes resolved to page/bbox by code, never by the model | Models hallucinate coordinates; grounding must be verifiable | Alt: model-supplied offsets | -
- 2026-09-29 | Logprobs never load-bearing | Not all OpenRouter providers return them (Anthropic doesn't) | Alt: logprob confidence | -
- 2026-09-29 | `usdm4` pinned exactly at 0.29.0 | Conformance results must be reproducible (PINS.md) | Alt: >= floor | -
- 2026-09-29 | OpenRouter default gateway, direct Anthropic fallback, stub last | Multi-model ensembles behind one key (llm/router.py) | Alt: single provider | -
- 2026-09-29 | Frontier LLMs by default; SLMs parked (--slm) | Published evidence favors frontier models (PLAN.md 4.2); accuracy over cost | Alt: small models for cost | -
