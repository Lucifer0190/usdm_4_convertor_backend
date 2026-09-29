# USDM4-Assure

> Convert clinical trial protocol PDFs into conformant **CDISC USDM 4.0** JSON — every
> field grounded in a verifiable citation, scored by a calibrated confidence, and triaged
> for human review with a 21 CFR Part 11 audit trail.

**Status:** Phases 0–6 of the v0.3 architecture implemented (see [`PLAN.md`](PLAN.md) §6) ·
**Python:** 3.12 · **License:** proprietary / internal (see [below](#license))

USDM4-Assure reads a protocol document and produces a structurally-valid, quote-grounded
USDM 4.0 study spanning **metadata, study design, eligibility, objectives, estimands,
organizations/sites, and the Schedule of Activities** — with every extracted field
provenance-tagged, cross-checked by independent methods, routed through a deterministic
section graph with prohibited-scope filtering, and triaged for human review through an
HTMX certification UI backed by a 21 CFR Part 11 audit trail. It runs with **no API keys
and no real data**: the extraction ensemble uses independent deterministic methods, and an
LLM member joins automatically via **OpenRouter** when a key is set (Claude direct also
works).

## Why — and what changed

A published-literature review ([`PLAN.md`](PLAN.md)) corrected two assumptions this
project started with: there is no single "~89%/~76% market ceiling" to beat (the two
figures traced to different, non-comparable studies), and independent-looking extraction
paths are far more correlated than assumed (measured cross-model error correlation is
0.74–0.82, not near-zero). The honest state of the art on this task is ~89% field-level
accuracy, with **silent omission** — a confident, complete-looking result quietly missing
data — as the dominant failure mode on real, long protocols.

USDM4-Assure's v0.3 design targets that failure mode directly (see
[docs/architecture.md](docs/architecture.md) and [`DESIGN.md`](DESIGN.md)):

| What actually breaks published systems | Our counter-mechanism |
|---|---|
| Silent omission on long/wide schemas | **Sharded extraction** + **completeness accounting** |
| Ungrounded values | **Mandatory verbatim quote**, resolved to page/coordinates by code, never the model |
| Table structure destroyed, especially across pages | **Specialist grid model + VLM content pass** + a custom multi-page stitcher |
| Dishonest confidence | **Multi-signal calibrated confidence** + a **conformal bound** on auto-accepted fields |

The accuracy contract is a **human-in-the-loop certification guarantee**, not zero-touch
output: the pipeline maximizes un-reviewed accuracy, makes confidence trustworthy so
review is surgical, and blocks non-conformant output at the conformance gate. "Full-proof"
conversion is not a claim any published system — including this one — can support; grounded,
calibrated, auditable output is.

## Quickstart

```bash
# Python 3.12 is required (the CDISC stack has no 3.13 wheel yet).
conda create -n usdm4 python=3.12 -y
conda run -n usdm4 python -m pip install -e ".[dev]"

# Generate a synthetic protocol and run the full loop (no real data needed).
conda run -n usdm4 python spikes/make_full_fixture.py
conda run -n usdm4 python -m usdm4_assure.cli convert-full data/fixtures/protocol_full.pdf
```

### CLI

| Command | Does |
|---|---|
| `usdm4 convert <pdf>` | Metadata-only spine (C1) → partial study + provenance review. |
| `usdm4 convert-soa <pdf>` | Extract a Schedule of Activities → USDM ScheduleTimeline entities. |
| `usdm4 convert-full <pdf>` | Full loop → one USDM 4.0 study across seven domains. `--previous <pdf>` diffs and assembles an amendment; `--core` runs the official CDISC CORE gate; `--require-llm` fails loudly instead of silently falling back to deterministic-only. |
| `usdm4 eval` | Score the pipeline against frozen field labels; writes the accuracy scoreboard. |
| `usdm4 roles` | Print the active OpenRouter model-role configuration. |

## What's built

- **Foundation → Extraction (L0–L4):** PyMuPDF ingest with char-level geometry, a
  multi-page Schedule-of-Activities stitcher with mechanical mark re-derivation, a
  deterministic section graph (bookmarks or heading blocks) with prohibited-scope
  filtering, and sharded two-pass extraction across six domains (C1 metadata, C2 design,
  C3 eligibility, C4 objectives, C5 estimands, C6 organizations/sites) plus the SoA.
- **Grounding + Assurance (L5–L6, the moat):** every LLM value carries a verbatim quote
  resolved to page/character-offset/bbox by code, never the model; one uniform
  ensemble + verifier + confidence path for every domain; completeness accounting
  (expected-vs-found); a calibrated confidence model and an SSBC-corrected conformal
  auto-accept threshold exist and are tested, but are not yet wired into the pipeline's
  own triage — too few frozen labels today to calibrate one responsibly (see
  [docs/pipeline.md](docs/pipeline.md)).
- **Assembly → Validation (L7–L8):** assembled via the data4knowledge `Assembler`, with a
  sanitizer that reports every input repair instead of applying it silently, per-section
  fallback (a bad section is dropped and the rest salvaged, with the assembler-reliance
  ratio reported), and a bounded (≤2-round) validate→re-extract→repair loop; structural,
  d4k (offline), and optional CORE conformance gates.
- **Certification (L9):** an HTMX review UI over a 21 CFR Part 11 append-only audit
  trail — click-to-source crops, audited edits, certification, post-edit-distance
  telemetry.
- **OpenRouter** as the default LLM gateway (multi-model, tiered by role), with a
  direct-Anthropic fallback and a drop-in SLM ensemble member (`--slm`).
- 445+ passing tests checking each domain against synthetic ground truth, plus real
  usdm_data corpus protocols where the section-graph/routing work depends on real
  document structure.
- Dockerized (`docker/`, `docker-compose.yml` — `app` + an optional `review` service).

See [`PLAN.md`](PLAN.md) §6 for the phased roadmap and [docs/scoreboard.md](docs/scoreboard.md)
for measured numbers across the usdm_data corpus.

## Documentation

Full docs in [`docs/`](docs/index.md):

- [Architecture](docs/architecture.md) — the ten layers and the evidence behind each one.
- [Pipeline & contracts](docs/pipeline.md) — data flow and the shared types.
- [Module reference](docs/modules.md) — what every package does, current and planned.
- [Conformance & limitations](docs/conformance.md) — the gates, current results, and an
  honest analysis of what's gated by the upstream assembler versus fixable from our side.
- [Scoreboard](docs/scoreboard.md) — measured auto-accept coverage, review burden,
  realized error, and assembler reliance ratio across the usdm_data corpus.
- [Review UI](docs/review.md) — the HTMX certification tool: click-to-source crops,
  audited edits, post-edit-distance telemetry.
- [Development](docs/development.md) — setup, testing, environment gotchas.
- [References](docs/references.md) — standards, tools, and prior art, with corrected
  citation scope.

Design and strategy background: [`DESIGN.md`](DESIGN.md) (v0.3 technical design),
[`PLAN.md`](PLAN.md) (the evidence review and roadmap behind it),
[`spikes/SPIKE_LOG.md`](spikes/SPIKE_LOG.md).

## Conformance status (honest)

The reference fixture is structurally valid, assembles with zero errors, and fails **5 of
213** d4k rules (down from 12 before Phase 6) — **not yet CORE-clean**. Most of the
reduction came from finding real bugs (a hidden exception-swallowing bug that made
assembler errors invisible since Phase 0; an invalid sponsor-identifier scope; an
out-of-range placeholder the assembler substitutes for a missing timing window), not from
extracting more data. Two rules remain genuinely gated by the **upstream data4knowledge
assembler or its bundled rule library**; one needs richer extraction this project
deliberately does not attempt (see the trade-off it would require). See
[docs/conformance.md](docs/conformance.md) for the rule-by-rule breakdown and
[docs/scoreboard.md](docs/scoreboard.md) for the full-corpus numbers.

## License

This project is **proprietary and internal to Hexaware (HTL practice)**. It is not
released under an open-source license. Do not redistribute without authorization.

Note: the `usdm4` package we build on is **GPL-3.0**. Internal use is not distribution,
so this is workable, but it is recorded here as a deliberate decision rather than an
oversight — see [`docs/references.md`](docs/references.md).
*(If this repository is intended to be open-sourced, replace this section with the chosen
license and add a `LICENSE` file — that is a deliberate decision, so it is left explicit
here rather than assumed.)*
