# Development

## Environment

**Python 3.12 is required.** The CDISC stack (`cdisc-rules-engine`, via `usdm4`) has no
Python 3.13 wheel yet and will try — and fail — to compile `pydantic-core` from Rust
source. Use a 3.12 environment.

```bash
conda create -n usdm4 python=3.12 -y
conda run -n usdm4 python -m pip install -e ".[dev]"
```

The project is also Dockerized (`docker/Dockerfile`, `docker-compose.yml`) targeting
`python:3.12-slim`, so the local PoC deploys unchanged elsewhere.

## API keys

Put keys in a `.env` file at the repo root (git-ignored); it is loaded automatically.
None are required to run the pipeline — the deterministic ensemble carries every run —
but they unlock additional capability.

| Variable | Unlocks |
|---|---|
| `OPEN_ROUTER_KEY` | **The default LLM gateway.** [OpenRouter](https://openrouter.ai) fronts many providers behind one key, so the ensemble can mix model families. The pipeline defaults to frontier models (Claude Sonnet 4.5, GPT-5.1, Gemini 3.1 Pro). Override with `USDM4_MODEL_<ROLE>` (e.g., `USDM4_MODEL_EXTRACT=anthropic/claude-opus-4.8`). |
| `USDM4_REQUIRE_LLM` | Set to `1` to hard-fail if no API key is configured (instead of silently falling back to stub). |
| `ANTHROPIC_API_KEY` | Fallback direct-Anthropic path, used only if no OpenRouter key is set. |
| `CDISC_LIBRARY_API_KEY` | The official CDISC CORE gate (`convert-full --core`) and controlled-terminology lookups. Free to register at the CDISC Library. |

> **v0.3 note:** logprobs are never load-bearing anywhere in this pipeline. OpenRouter
> accepts a `logprobs` parameter, but not every routed provider returns it — Anthropic does
> not — so a design that depends on it breaks silently on a model swap. See
> [`../DESIGN.md`](../DESIGN.md) §4 and [`../PLAN.md`](../PLAN.md) for why.

The LLM resolution order is OpenRouter → direct Anthropic → stub (see `llm/router.py`).
With a key present, the Claude member joins the Assurance ensemble as an additional
independent path, which lifts agreement and auto-accept (e.g. metadata auto-accept went
from 1/6 to 5/6 on the reference fixture).

### Role-based model selection

Models are selected by role (e.g., `extract`, `verify`, `vision`) not by tier. See
`config/models.yaml` for the mapping and [`../PLAN.md`](../PLAN.md) §4.1 for the rationale
behind each choice. **All roles use frontier models by default** (Claude Sonnet 4.5, GPT-5.1,
Gemini 3.1 Pro). Override any role with `USDM4_MODEL_<ROLE>` environment variable
(e.g., `USDM4_MODEL_VERIFY=anthropic/claude-opus-4.8`).

> **v0.3 note — SLM experimental opt-in:** Earlier versions used small models like
> Llama-3.1-8B as a second ensemble member to improve metadata auto-accept. Published
> evidence shows frontier models now outperform SLMs in every measured domain (see
> [`../PLAN.md`](../PLAN.md) §4.2). The `--slm` flag is parked but not removed — if a
> future eval shows a domain where frontier accuracy falls below an SLM's published
> benchmark, that SLM can return via config change only. OpenRouter has no clinical
> fine-tuned model in its catalog (checked 60 providers / 411 models); a true clinical
> SLM would require fine-tuning from reviewer corrections, part of the Learning layer
> planned for Phase 5+.

### Tests never call a live model

`tests/conftest.py` sets `USDM4_NO_LLM=1`, which forces the router to the stub so the
suite stays fast, free, offline, and deterministic even when a key is present. Set the
same variable yourself to run the deterministic-only path from the CLI.

## Running

```bash
# generate synthetic fixtures (no real/sensitive protocol data needed)
conda run -n usdm4 python spikes/make_fixture.py        # metadata-only
conda run -n usdm4 python spikes/make_soa_fixture.py     # SoA table
conda run -n usdm4 python spikes/make_full_fixture.py    # full protocol

# run the CLI
conda run -n usdm4 python -m usdm4_assure.cli convert       data/fixtures/protocol_ABC123.pdf
conda run -n usdm4 python -m usdm4_assure.cli convert-soa   data/fixtures/protocol_soa.pdf
conda run -n usdm4 python -m usdm4_assure.cli convert-full  data/fixtures/protocol_full.pdf
```

## Testing

```bash
conda run -n usdm4 python -m pytest tests/ -q
```

The suite (445+ tests) checks each domain's extraction against synthetic ground truth, the
SoA cross-validation and stitching, section-graph routing and scope filtering against real
usdm_data corpus protocols (skipped when the gitignored corpus isn't cloned), the sanitizer/
fallback/repair loop against the real usdm4 assembler and conformance rule engine, and that
the full loop assembles a structurally-valid study. The first CORE-related import can be
slow on a cold cache. `tests/conftest.py` also redirects the Part 11 audit store to a temp
directory, so running the suite never writes into the real `data/audit/`.

## Environment gotchas

- **`conda run` and multi-line `-c`**: `conda run -n env python -c "<multi-line>"` fails
  (`conda` rejects newline arguments). Always put throwaway scripts in a file and run the
  file. Scratch probes live under `spikes/` and are prefixed `_`.
- **Serializing assembled studies**: `wrapper.model_dump()` leaves `UUID`/enum objects in
  the dict; serialize with `json.dumps(obj, default=str)`.
- **d4k result objects**: `RulesValidationResults.passed` / `.count` / `.finding_count`
  are **properties, not methods** — read them defensively (see `validate/gate.py::_get`).

## Layout

```
src/usdm4_assure/   the package (see docs/modules.md)
tests/              pytest suite (ground-truth checks)
spikes/             fixtures (make_*.py), the spike log, and scratch probes (_*.py)
docs/               this documentation
docker/             Dockerfile; compose at repo root
DESIGN.md           the v0.3 technical design (architecture layer)
PLAN.md             the evidence review and phased roadmap behind v0.3
```

## Documentation site (optional)

The docs are plain Markdown and render on any Git host as-is. To serve them as a site,
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) is a good fit for a
CLI/developer product. An `mkdocs.yml` is provided; note that MkDocs core has slowed in
2026, so check the maintained fork your plugins target before committing to it.
