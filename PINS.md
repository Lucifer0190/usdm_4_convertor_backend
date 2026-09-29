# Version pins

Conformance is version-dependent in three independent ways (docs/ai/archive/PLAN-v0.3-evidence-and-roadmap.md §1, conformance.md).
This page is the single place all three are recorded, so a future upgrade is a deliberate
decision, not drift. Update this table whenever any of the three moves.

| Pin | Value | Source | Why it matters |
|---|---|---|---|
| `usdm4` package version | **0.29.0**, exact (`pyproject.toml`) | [data4knowledge/usdm4](https://github.com/data4knowledge/usdm4) commit [`ebf7cdb`](https://github.com/data4knowledge/usdm4/commit/ebf7cdbcafd341de77dd1072446a7e65e9a8d276) (2026-08-10), `src/usdm4/__info__.py` | Fixes the model, the Assembler, the Builder, and the bundled d4k rule set all at once. The currently vendored spike copy (`spikes/_work/usdm4-src`, gitignored) is this exact commit and is *newer than the `>=0.28.0` floor previously in `pyproject.toml`* — it already fixes two bugs an earlier spike logged as open (`AmendmentsAssembler` crash on `None` enrollment; `AssemblerInput.soa` accepting only one timeline). Pinning exact, not a floor, means the Phase 0 assembler pass-rate measurement (`spikes/measure_assembler.py`) stays reproducible until this line is bumped on purpose. |
| USDM data model version | **4.0.0** | `src/usdm4/__info__.py` `__model_version__` | The schema every extracted field is validated against (Gate 1, `validate/gate.py`). |
| CDISC CORE rule-set version | **`cdisc-rules-engine>=0.16.0`** (as pinned by `usdm4` 0.29.0's own `requirements.txt`; not independently pinned by us today) | `spikes/_work/usdm4-src/setup.py`, `spikes/_work/usdm4-src/requirements.txt` | Gate 3 (`validate_core`, needs `CDISC_LIBRARY_API_KEY`). A floor, not an exact pin, because `usdm4` itself only floors it — tightening this to an exact version is a Phase 0/1 follow-up once CORE is run for real (`spikes/run_core_corpus.py`, Phase 7). |
| USDM v4.0 errata revision | **Not separately tracked yet** — as of the v0.3 design review, 27 errata had been published against USDM v4.0, some flipping a rule's severity between ERROR and WARNING (`docs/conformance.md`, `docs/references.md`). | [CDISC Library](https://library.cdisc.org) errata page (external; re-check before every CORE run) | Rule severity is data pulled from a source that changes independently of the `usdm4`/CORE package versions above. Treating it as a hardcoded constant would silently drift. |

## Why three pins, not one

`usdm4` bundles a model *and* a rule engine *and* an assembler, so it is tempting to treat
"the `usdm4` version" as the only pin that matters. It isn't: CORE's rule content updates on
its own release cadence (already `>=0.16.0` as a floor inside `usdm4` 0.29.0, and CDISC
publishes errata **independently of any package release**). A conformance number is only
reproducible if all three are recorded together, which is what this table is for.

## Updating this file

When any pin changes:
1. Re-run `spikes/measure_assembler.py` and compare the pass-rate to the last recorded run
   in `spikes/reports/`.
2. Re-run the full test suite (`pytest`).
3. Update this table and the relevant row in `docs/conformance.md`.
4. Note the change in `CHANGELOG.md`.
