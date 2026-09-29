---
paths:
  - "src/usdm4_assure/extract/**"
  - "src/usdm4_assure/assure/**"
  - "src/usdm4_assure/ground/**"
  - "src/usdm4_assure/llm/prompts/**"
  - "src/usdm4_assure/pipeline.py"
---

# Extraction and assurance rules

- Grounding contract: an LLM value must carry a verbatim quote. `ground/quote.py::resolve_quote` resolves it
  to page/offset/bbox in code. The model never supplies coordinates. A value backed only by a failed quote is
  a hard BLOCK (`assure/__init__.py`).
- Every domain goes through the one uniform `assure.assure()` path (ensemble, grounding, verifier,
  confidence). Don't add a per-domain confidence formula.
- Don't modify the Assurance layer or the gates to make a domain pass. If a value can't be verified it must
  route to review, not be forced through.
- Adding a domain: `extract/<domain>.py` returns `FieldCandidate`s or `GroundedCandidate`s; run scalars
  through `assure.assure()`; map into `AssemblerInput` in `assemble/study.py`; add a ground-truth fixture and
  a test; re-run the conformance report and record rule changes in CHANGELOG.md.
- Prompts live in `llm/prompts/<domain>.pass1.md` / `.pass2.md`. A prompt or model change is a possible
  accuracy regression: re-run the suite and report the result.
- Logprobs are never load-bearing; not every routed provider returns them.
- Independent-looking extraction paths are correlated (0.74-0.82 measured across models). Don't treat
  agreement between two LLMs as strong evidence; prefer deterministic, source-independent checks.
- Silent omission is the dominant failure mode: report what was expected vs found rather than returning a
  complete-looking result with data missing.
