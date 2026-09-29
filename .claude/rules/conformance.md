---
paths:
  - "src/usdm4_assure/validate/**"
  - "src/usdm4_assure/assemble/**"
  - "PINS.md"
  - "docs/conformance.md"
---

# Conformance and assembly rules

- The sanitizer reports every input repair; never apply a repair silently. Assembly falls back per section
  (a bad section is dropped, the rest salvaged) and reports the assembler-reliance ratio.
- The validate -> re-extract -> repair loop is bounded (<= 2 rounds). Don't raise the bound to hide failures.
- d4k result fields (`.passed`, `.count`, `.finding_count`) are properties; read them defensively
  (`validate/gate.py::_get`).
- Serialize assembled studies with `json.dumps(obj, default=str)`.
- Conformance depends on three pins: the `usdm4` version, the USDM model version, and the CORE rule set.
  When any moves: re-run `spikes/measure_assembler.py`, run the full suite, update `PINS.md` and the
  matching row in `docs/conformance.md`, then add a CHANGELOG.md entry.
- When a change affects d4k/CORE findings, update `docs/conformance.md` with the new counts, and say if a rule
  moves between the "upstream-gated" and "we-can-fix" buckets.
- The CORE gate needs `CDISC_LIBRARY_API_KEY`; without it, report the result as skipped, never as a pass.
