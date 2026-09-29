# USDM4-Assure

**Convert clinical trial protocol PDFs into conformant CDISC USDM 4.0 JSON — with a
grounding layer that cites every field back to its source, and an assurance layer that
turns confidence into a statistically-bounded auto-accept decision.**

USDM4-Assure is a Python pipeline that reads a protocol document and produces a
structurally-valid USDM 4.0 study spanning metadata, study design, eligibility,
objectives, interventions, and the Schedule of Activities — with every extracted
field provenance-tagged, cross-checked, and triaged for human review.

## Why it exists — and what changed in v0.3

A literature review of the published protocol-extraction and document-AI research
([full findings](../PLAN.md)) corrected two assumptions the project started with: there is
no single "~89%/~76% market ceiling" to beat (the two figures aren't a matched benchmark),
and independent-looking extraction paths are not nearly as independent as assumed
(measured cross-model error correlation is 0.74–0.82). The honest published state of the
art is ~89% field-level accuracy with a **silent-omission** failure mode on long
documents — a confident, well-formed result that is quietly missing data.

USDM4-Assure's v0.3 design targets that failure mode directly:

| What actually breaks published systems | Our counter-mechanism |
|---|---|
| Silent omission on long/wide schemas | **Sharded extraction** + **completeness accounting** (expected vs found) |
| Ungrounded values | **Mandatory verbatim quote**, resolved to page/coordinates by code, never by the model |
| Table structure destroyed, especially across pages | **Specialist grid model + VLM content pass** + a custom multi-page stitcher |
| Dishonest confidence | **Multi-signal calibrated confidence** + a **conformal bound** on auto-accepted fields |

See [Architecture](architecture.md) for how these map onto the code, and
[`../DESIGN.md`](../DESIGN.md) for the full design with citations.

## The accuracy contract

"100% accuracy for clinical use" is a **human-in-the-loop certification guarantee**,
not zero-touch output. The pipeline maximizes *un-reviewed* accuracy, makes confidence
trustworthy so review is surgical, and blocks non-conformant output at the CORE gate.
The clinical guarantee comes from Grounding + Assurance + the conformance gate + SME
sign-off — not from a claim of "full-proof" conversion, which the published evidence does
not support for any system.

## Quickstart

```bash
# Python 3.12 is required (the CDISC stack has no 3.13 wheel yet).
conda create -n usdm4 python=3.12 -y
conda run -n usdm4 python -m pip install -e ".[dev]"

# Generate a synthetic protocol and run the full loop.
conda run -n usdm4 python spikes/make_full_fixture.py
conda run -n usdm4 python -m usdm4_assure.cli convert-full data/fixtures/protocol_full.pdf
```

No API keys and no real data are required to run the pipeline: the extraction ensemble
uses independent deterministic methods, and an LLM member joins automatically via
**OpenRouter** when a key is present (Claude direct also works). See
[Development](development.md) for full setup.

## Documentation map

- **[Architecture](architecture.md)** — the ten layers and the evidence behind each one.
- **[Pipeline & contracts](pipeline.md)** — how data flows and the types each layer speaks.
- **[Module reference](modules.md)** — what every package does, current and planned.
- **[Conformance & limitations](conformance.md)** — the validation gates, current results,
  and the honest analysis of what's gated by the upstream assembler.
- **[Review UI](review.md)** — the HTMX certification tool: click-to-source crops, audited
  edits, post-edit-distance telemetry.
- **[Development](development.md)** — setup, testing, and environment gotchas.
- **[References](references.md)** — standards, tools, and prior art, with the accuracy
  claims each source actually supports.
- **[`../PLAN.md`](../PLAN.md)** — the full evidence review and phased roadmap.
- **[`../DESIGN.md`](../DESIGN.md)** — the complete v0.3 technical design.

## Status

Phases 0–6 of the v0.3 architecture (see [`../PLAN.md`](../PLAN.md) §6) are implemented:
one protocol PDF → a structurally-valid, quote-grounded USDM 4.0 study across seven domains
(metadata, design, eligibility, objectives, estimands, organizations/sites, Schedule of
Activities), routed through a section graph with prohibited-scope filtering, a Part 11 audit
trail, an HTMX certification UI, and a bounded validate→re-extract→repair loop — 445 passing
tests, fully Dockerized. See [Conformance](conformance.md) for exactly where CORE-clean
output stands today (down to 5 failing d4k rules on the reference fixture, from 12).
