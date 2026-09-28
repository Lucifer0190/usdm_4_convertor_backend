"""Pipeline orchestration — wires the layers into runnable end-to-end flows.

Two entry points:

* :func:`run` — the metadata-only spine (C1). The smallest slice that exercises
  every layer: Foundation(ingest) -> Extraction -> Assurance -> Integrity.
* :func:`run_full` — the full loop: metadata (C1) + design (C2) + eligibility (C3)
  + objectives (C4) + Schedule of Activities, assembled into one USDM 4.0 study.

Both share the same pattern, which is the point of the architecture: adding a
domain is another extractor feeding the same Assurance + assemble path, not a
rewrite. See ``docs/pipeline.md`` for the data-flow contracts.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from usdm4_assure.assemble.metadata import assemble_metadata
from usdm4_assure.assure import assure
from usdm4_assure.assure.completeness import account, demote_on_error
from usdm4_assure.audit.store import AuditStore, record_source
from usdm4_assure.audit.writer import write_run
from usdm4_assure.contracts import AssuredField, Decision, FieldCandidate, Finding
from usdm4_assure.extract import metadata as c1
from usdm4_assure.extract.design import DESIGN_FIELDS
from usdm4_assure.extract.eligibility import EligibilityExtract
from usdm4_assure.extract.objectives import ObjectivesExtract
from usdm4_assure.extract.shards import ELIGIBILITY_FIELDS, OBJECTIVES_FIELDS
from usdm4_assure.extract.windows import window_for
from usdm4_assure.ingest.pdf import ingest
from usdm4_assure.llm.router import get_llm
from usdm4_assure.sections.plan import build_plan
from usdm4_assure.validate.gate import validate_wrapper


def _sha256_file(path: str | Path) -> str:
    """Hex sha256 of a file's bytes — the audit store's identity for a source PDF."""
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def _eligibility_candidates(e: EligibilityExtract) -> list[FieldCandidate]:
    """Bridge the C3 deterministic extract into field-level candidates for
    :func:`assure`, so eligibility drops its own ad hoc confidence/decision
    in favor of the one uniform assurance path (DESIGN.md L6)."""
    cands: list[FieldCandidate] = []
    if e.inclusion:
        text = " ".join(e.inclusion)
        cands.append(FieldCandidate("inclusionCriteria", text, "region-parser", text))
    if e.exclusion:
        text = " ".join(e.exclusion)
        cands.append(FieldCandidate("exclusionCriteria", text, "region-parser", text))
    if e.age_min is not None:
        v = str(e.age_min)
        cands.append(FieldCandidate("plannedMinimumAge", v, "region-parser", v))
    if e.age_max is not None:
        v = str(e.age_max)
        cands.append(FieldCandidate("plannedMaximumAge", v, "region-parser", v))
    cands.append(FieldCandidate("plannedSex", e.sex, "region-parser", e.sex))
    return cands


def _objectives_candidates(o: ObjectivesExtract) -> list[FieldCandidate]:
    """Bridge the C4 deterministic extract into field-level candidates for
    :func:`assure` (see :func:`_eligibility_candidates`)."""
    cands: list[FieldCandidate] = []
    for item in o.items:
        obj_field = "primaryObjective" if item.level == "Primary" else "secondaryObjective"
        cands.append(FieldCandidate(obj_field, item.objective, "label-parser", item.objective))
        if item.endpoint:
            end_field = "primaryEndpoint" if item.level == "Primary" else "secondaryEndpoint"
            cands.append(FieldCandidate(end_field, item.endpoint, "label-parser", item.endpoint))
    return cands


@dataclass
class FullResult:
    """Everything the full pipeline produced for one protocol.

    Attributes:
        assured_meta: Metadata (C1) fields after the Assurance layer.
        design: The ``DesignExtract`` (C2) — study type, model, arms.
        grid: The ``AssuredGrid`` — the cross-validated Schedule of Activities.
        study: The ``build_full_study`` output dict (wrapper, validation, summary).
        out_dir: Directory the artifacts were written to.
        eligibility: The ``EligibilityExtract`` (C3), or ``None``.
        objectives: The ``ObjectivesExtract`` (C4), or ``None``.
        assured_design: C2's scalar fields (studyType, interventionModel)
            after the Assurance layer.
        assured_eligibility: C3's fields after the Assurance layer.
        assured_objectives: C4's fields after the Assurance layer.
        routed: The section graph + route plan (``None`` with routing off).
        findings: Scope findings from every domain's evidence window.
        windows: ``{domain: EvidenceWindow}`` for metadata/design/eligibility/
            objectives — the input ``assure.features`` needs for retrieval
            signals (task 4.2).
        source_sha256: The source PDF's sha256 — the audit store's key, and
            what the review UI (task 5.1) looks a run up by.
        run_id: This run's id in the audit store.
    """
    assured_meta: list[AssuredField]
    design: object
    grid: object
    study: dict
    out_dir: Path
    eligibility: object = None
    objectives: object = None
    assured_design: list[AssuredField] = field(default_factory=list)
    assured_eligibility: list[AssuredField] = field(default_factory=list)
    assured_objectives: list[AssuredField] = field(default_factory=list)
    routed: object = None
    findings: list[Finding] = field(default_factory=list)
    windows: dict = field(default_factory=dict)
    source_sha256: str = ""
    run_id: str = ""


def run_full(pdf_path: str | Path, out_dir: str | Path = "data/out_full",
             run_core: bool = False, use_slm: bool = False,
             routing: bool = True) -> FullResult:
    """Run the full loop: PDF -> C1 metadata + C2 design + C3/C4 + SoA -> one study.

    Ingests the PDF once, runs every domain extractor over it, reconciles the SoA
    with two independent table methods, then assembles a single conformant USDM 4.0
    study via the data4knowledge assembler and validates it. Writes
    ``study.usdm.json`` to ``out_dir`` when assembly succeeds.

    Args:
        pdf_path: Path to the source protocol PDF.
        out_dir: Directory for artifacts (rendered pages + assembled study JSON).
        run_core: If ``True``, also run the official CDISC CORE gate (requires
            ``CDISC_LIBRARY_API_KEY``); otherwise only the offline d4k gate runs.
        routing: Build the section graph + route plan and give each domain a
            scoped evidence window (task 3.5). ``False`` feeds every extractor
            the whole document — the routing-off arm of the Phase 3 eval.

    Returns:
        A ``FullResult`` bundling every domain's extract, the assembled study,
        its validation report, and the output directory.
    """
    from usdm4_assure.assemble.study import build_full_study
    from usdm4_assure.extract.design import extract_design
    from usdm4_assure.extract.eligibility import extract_eligibility
    from usdm4_assure.extract.objectives import extract_objectives
    from usdm4_assure.extract.soa.crossval import cross_validate
    from usdm4_assure.extract.soa.methods import (
        extract_pdfplumber,
        extract_pymupdf,
        extract_pymupdf_stitched,
    )

    pdf_path, out_dir = Path(pdf_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = ingest(pdf_path, image_dir=out_dir / "pages")
    members = _members(use_slm)
    routed = build_plan(doc, pdf_path) if routing else None
    win = {d: window_for(doc, routed, d)
           for d in ("metadata", "design", "eligibility", "objectives")}
    findings = [f for w in win.values() for f in w.findings]

    meta_doc = win["metadata"].document
    assured_meta = assure(c1.extract_all(meta_doc, members), meta_doc, c1.FIELDS,
                          domain="metadata")
    meta = {a.field: a.value for a in assured_meta if a.value}
    design_doc = win["design"].document
    design_cands, design = extract_design(design_doc, meta, members[0])
    assured_design = assure(design_cands, design_doc, DESIGN_FIELDS, domain="design")
    elig_doc = win["eligibility"].document
    elig = extract_eligibility(elig_doc)
    assured_eligibility = assure(_eligibility_candidates(elig), elig_doc, ELIGIBILITY_FIELDS,
                                 domain="eligibility")
    obj_doc = win["objectives"].document
    objs = extract_objectives(obj_doc)
    assured_objectives = assure(_objectives_candidates(objs), obj_doc, OBJECTIVES_FIELDS,
                                domain="objectives")
    # The stitcher (task 2.3) is multi-page-aware; a table it can't confidently
    # reduce to the 3-header-row shape falls back to the single-page path.
    pymupdf_grid = extract_pymupdf_stitched(pdf_path) or extract_pymupdf(pdf_path)
    grid = cross_validate([extract_pdfplumber(pdf_path), pymupdf_grid])

    study = build_full_study(assured_meta, design, grid, elig, objs, run_core=run_core)
    if study.get("wrapper"):
        (out_dir / "study.usdm.json").write_text(
            json.dumps(study["wrapper"], indent=2, default=str), encoding="utf-8")

    all_assured = assured_meta + assured_design + assured_eligibility + assured_objectives
    # Completeness (task 3.6): expected-vs-found across domains, over current-scope text.
    gaps = account(design=design, grid=grid, eligibility=elig, objectives=objs,
                   wrapper=study.get("wrapper"), evidence_text=design_doc.full_text)
    findings += gaps
    demote_on_error(all_assured, gaps)

    # Part 11 audit trail (DESIGN.md L9): one AuditRecord per final field decision,
    # written after completeness may have demoted a decision, so the trail matches
    # what review.json reports. record_source() is what lets the review UI (Phase 5)
    # find this PDF again from just its sha256.
    source_sha256 = _sha256_file(pdf_path)
    run_id = uuid.uuid4().hex
    record_source(source_sha256, pdf_path)
    audit_store = AuditStore(source_sha256=source_sha256)
    for domain, fields_ in (("metadata", assured_meta), ("design", assured_design),
                            ("eligibility", assured_eligibility),
                            ("objectives", assured_objectives)):
        write_run(audit_store, run_id=run_id, source_sha256=source_sha256, domain=domain,
                 assured_fields=fields_, retrieval_config=win[domain].retrieval_config())
    audit_store.close()

    review = {
        "source": str(pdf_path),
        "decision_summary": {d.value: 0 for d in Decision},
        "fields": [a.as_review_row() for a in all_assured],
        "findings": [f.as_row() for f in findings],
        "routing": ({"route_plan_hash": routed.plan_hash,
                     "graph_source": routed.graph.source,
                     "sections": len(routed.graph.sections),
                     "study_archetype": routed.plan.fingerprint.study_archetype,
                     "windows": {d: w.retrieval_config() for d, w in win.items()}}
                    if routed else None),
        "validation": study.get("validation"),
    }
    for a in all_assured:
        review["decision_summary"][a.decision.value] += 1
    (out_dir / "review.json").write_text(json.dumps(review, indent=2), encoding="utf-8")

    return FullResult(assured_meta, design, grid, study, out_dir, elig, objs,
                      assured_design, assured_eligibility, assured_objectives,
                      routed=routed, findings=findings, windows=win,
                      source_sha256=source_sha256, run_id=run_id)


@dataclass
class PipelineResult:
    """Result of the metadata-only spine (:func:`run`).

    Attributes:
        assured: The metadata fields after the Assurance layer.
        wrapper: The assembled (partial) USDM 4.0 wrapper dict.
        validation: The conformance-gate report (structural + d4k + core).
        llm_name: Which LLM member ran (``"claude"`` or ``"stub"``).
        out_dir: Directory the artifacts were written to.
    """
    assured: list[AssuredField]
    wrapper: dict
    validation: dict
    llm_name: str
    out_dir: Path

    @property
    def review_stats(self) -> dict:
        """Count of fields per triage decision (auto_accept / review / block)."""
        c = {d.value: 0 for d in Decision}
        for a in self.assured:
            c[a.decision.value] += 1
        return c


def _members(use_slm: bool) -> list:
    """The LLM ensemble members: the primary (Claude) plus an optional SLM.

    Claude-only by default (cost control); ``use_slm`` adds a cheap different-family
    SLM member, which strengthens the cross-family agreement signal.
    """
    from usdm4_assure.llm.router import get_slm
    members = [get_llm()]
    if use_slm:
        members.append(get_slm())
    return members


def run(pdf_path: str | Path, out_dir: str | Path = "data/out",
        run_core: bool = False, use_slm: bool = False) -> PipelineResult:
    """Run the metadata-only spine (C1) end-to-end and write artifacts.

    The smallest demonstration of the architecture: ingest -> extract metadata
    -> Assurance -> assemble a partial study -> validate. Writes
    ``study.usdm.json`` and ``review.json`` (provenance + per-field triage).

    Args:
        pdf_path: Path to the source protocol PDF.
        out_dir: Directory for the output artifacts.
        run_core: If ``True``, additionally run the CDISC CORE gate.
        use_slm: If ``True``, add a cheap SLM member (different family than Claude)
            to the ensemble. Off by default for cost control.

    Returns:
        A ``PipelineResult`` with the assured fields, assembled wrapper, and
        validation report.
    """
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Foundation
    doc = ingest(pdf_path, image_dir=out_dir / "pages")

    # Extraction (C1) + LLM member(s) if a key is present
    members = _members(use_slm)
    llm = members[0]
    candidates = c1.extract_all(doc, members)

    # Assurance ★
    assured = assure(candidates, doc, c1.FIELDS, domain="metadata")

    # Integrity: assemble -> validate
    wrapper = assemble_metadata(assured)
    validation = validate_wrapper(wrapper, run_core=run_core)

    # Emit artifacts
    (out_dir / "study.usdm.json").write_text(
        json.dumps(wrapper, indent=2), encoding="utf-8")
    review = {
        "source": str(pdf_path),
        "llm": llm.name,
        "decision_summary": {d.value: 0 for d in Decision},
        "fields": [a.as_review_row() for a in assured],
        "validation": validation,
    }
    for a in assured:
        review["decision_summary"][a.decision.value] += 1
    (out_dir / "review.json").write_text(
        json.dumps(review, indent=2), encoding="utf-8")

    return PipelineResult(assured, wrapper, validation, llm.name, out_dir)
