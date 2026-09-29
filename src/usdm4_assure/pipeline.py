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
from usdm4_assure.contracts import (
    AssuredField,
    Decision,
    Document,
    Finding,
    FindingKind,
    Severity,
)
from usdm4_assure.extract import metadata as c1
from usdm4_assure.extract.domains import extract_domain
from usdm4_assure.extract.estimands import estimand_evidence, extract_estimands
from usdm4_assure.extract.sites import FIELDS as SITES_FIELDS
from usdm4_assure.extract.sites import extract_sites
from usdm4_assure.extract.windows import window_for
from usdm4_assure.ingest.pdf import ingest
from usdm4_assure.llm.router import get_llm, get_role_llm
from usdm4_assure.sections.plan import build_plan
from usdm4_assure.sections.slots import slot_document, strip_furniture
from usdm4_assure.validate.gate import validate_wrapper
from usdm4_assure.validate.repair import repair_loop


def _sha256_file(path: str | Path) -> str:
    """Hex sha256 of a file's bytes — the audit store's identity for a source PDF."""
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def _failed_rules(study: dict) -> list[str]:
    """Rule ids that failed any rule gate that ran (d4k, and CORE when enabled)."""
    validation = study.get("validation") or {}
    return sorted({r for gate in ("d4k", "core")
                   for r in ((validation.get(gate) or {}).get("failed_rules") or [])})


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
        estimands: The reconciled ``EstimandsExtract`` (C5, task 6.1).
        amendment_diff: The section-level ``AmendmentDiff`` against
            ``previous_version`` (task 6.2), or ``None``.
        repair: The bounded repair loop's ``RepairOutcome`` (task 6.3).
        assured_sites: C6's organization/role fields (task 6.4) after the
            Assurance layer.
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
    estimands: object = None
    amendment_diff: object = None
    repair: object = None
    assured_sites: list[AssuredField] = field(default_factory=list)


def run_full(pdf_path: str | Path, out_dir: str | Path = "data/out_full",
             run_core: bool = False, use_slm: bool = False,
             routing: bool = True, previous_version: str | Path | None = None,
             amendment_identifier: str | None = None) -> FullResult:
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
        previous_version: The prior version of this protocol. When given, the
            two are diffed section by section (task 6.2) and the result is
            assembled as a USDM ``StudyAmendment``.
        amendment_identifier: The amendment's number; defaults to the
            extracted ``studyVersionIdentifier``.

    Returns:
        A ``FullResult`` bundling every domain's extract, the assembled study,
        its validation report, and the output directory.
    """
    from usdm4_assure.assemble.study import build_full_study
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
           for d in ("metadata", "design", "eligibility", "objectives", "estimands", "sites")}
    findings = [f for w in win.values() for f in w.findings]

    # Section-level evidence (sections/slots.py): each domain reads its own section,
    # not the whole protocol, with running headers/footers removed. A slot that is
    # not found falls back to the routed window and says so.
    inputs, soa_pages, slot_findings = _domain_inputs(pdf_path, win, routed)
    findings += slot_findings
    llm_primary, llm_alt = get_role_llm("extract"), get_role_llm("extract_alt")

    def read(domain: str, meta_values: dict | None, escalate):
        window_doc, scoped = inputs[domain]
        return extract_domain(domain, window_doc, members, meta_values, escalate=escalate,
                              scoped=scoped)

    # First pass: the grounded two-pass LLM readers run here, on the narrow windows,
    # instead of only as a repair-loop escalation (which never fired in a real run).
    state = {"metadata": read("metadata", None, [llm_primary, llm_alt])}
    meta = state["metadata"].values()
    state["design"] = read("design", meta, [llm_primary, llm_alt])
    state["eligibility"] = read("eligibility", meta, llm_primary)
    state["objectives"] = read("objectives", meta, llm_primary)
    # C5 estimands (task 6.1): the hard_reasoning role plus a different-family
    # extract_alt member on top of the deterministic parser.
    estimands = extract_estimands(
        estimand_evidence(win["estimands"].document, routed),
        [get_role_llm("hard_reasoning"), get_role_llm("extract_alt")])
    assured_estimands = estimands.assured_fields()
    findings += estimands.findings
    # C6 organizations/sites (task 6.4): deterministic + one grounded LLM member.
    # Its own domain (in review.json/audit) but attached post-assembly, not
    # assembled from a shard — see assemble.sites.attach_organizations.
    sites_doc = win["sites"].document
    sites_cands = extract_sites(sites_doc, get_role_llm("route"))
    assured_sites = assure(sites_cands, sites_doc, SITES_FIELDS, domain="sites")
    sites_values = {a.field: a.value for a in assured_sites if a.value}
    # The stitcher (task 2.3) is multi-page-aware; a table it can't confidently
    # reduce to the 3-header-row shape falls back to the single-page path.
    # ``soa_pages`` is the schedule-of-activities section's page range (None when the
    # outline has no such section): without it "the table with most activities" was
    # an abbreviation glossary.
    pymupdf_grid = (extract_pymupdf_stitched(pdf_path, soa_pages)
                    or extract_pymupdf(pdf_path, soa_pages))
    grid = cross_validate([extract_pdfplumber(pdf_path, soa_pages), pymupdf_grid])

    amendment_diff, amendments_data = None, None
    if previous_version is not None:
        from usdm4_assure.assemble.amendments import amendment_input
        from usdm4_assure.extract.amendments import diff_versions
        from usdm4_assure.sections.graph import build_graph
        prev_doc = ingest(previous_version)
        amendment_diff = diff_versions(
            prev_doc, doc, build_graph(prev_doc, previous_version),
            routed.graph if routed else build_graph(doc, pdf_path))
        amendments_data, amendment_findings = amendment_input(
            amendment_diff,
            identifier=amendment_identifier or meta.get("studyVersionIdentifier") or "1")
        findings += amendment_diff.findings + amendment_findings

    def build(st: dict) -> dict:
        return build_full_study(st["metadata"].fields, st["design"].extract, grid,
                                st["eligibility"].extract, st["objectives"].extract,
                                run_core=run_core, estimands=estimands,
                                amendments=amendments_data, sites=sites_values)

    def revalidate(st: dict) -> list[str]:
        nonlocal study
        study = build(st)
        return _failed_rules(study)

    def reextract(domain: str, rnd: int):
        # Same section-level inputs as the first pass; round 2 adds the
        # hard_reasoning member.
        window_doc, scoped = inputs[domain]
        return extract_domain(domain, window_doc, members, state["metadata"].values(),
                              escalate=get_role_llm("hard_reasoning") if rnd > 1 else None,
                              scoped=scoped)

    # Bounded repair loop (task 6.3, DESIGN.md L8): validate -> re-extract -> re-validate.
    study = build(state)
    repair = repair_loop(_failed_rules(study), state, reextract=reextract,
                         revalidate=revalidate)
    findings += study.get("findings", []) + repair.findings
    if study.get("wrapper"):
        (out_dir / "study.usdm.json").write_text(
            json.dumps(study["wrapper"], indent=2, default=str), encoding="utf-8")

    assured_meta, assured_design, assured_eligibility, assured_objectives = (
        state[d].fields for d in ("metadata", "design", "eligibility", "objectives"))
    design, elig, objs = (state[d].extract for d in ("design", "eligibility", "objectives"))
    all_assured = (assured_meta + assured_design + assured_eligibility + assured_objectives
                   + assured_estimands + assured_sites)
    # Completeness (task 3.6): expected-vs-found across domains, over current-scope text.
    gaps = account(design=design, grid=grid, eligibility=elig, objectives=objs,
                   wrapper=study.get("wrapper"), evidence_text=win["design"].document.full_text)
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
                            ("objectives", assured_objectives),
                            ("estimands", assured_estimands),
                            ("sites", assured_sites)):
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
        "assembly": study.get("assembly"),
        "repair": {"rounds": repair.rounds, "resolved": repair.resolved,
                   "unresolved": repair.unresolved,
                   "adopted": [f"round {r}: {d}" for r, d in repair.adopted]},
    }
    for a in all_assured:
        review["decision_summary"][a.decision.value] += 1
    (out_dir / "review.json").write_text(json.dumps(review, indent=2), encoding="utf-8")

    return FullResult(assured_meta, design, grid, study, out_dir, elig, objs,
                      assured_design, assured_eligibility, assured_objectives,
                      routed=routed, findings=findings, windows=win,
                      source_sha256=source_sha256, run_id=run_id, estimands=estimands,
                      amendment_diff=amendment_diff, repair=repair, assured_sites=assured_sites)


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


def _merged(*docs: Document | None) -> Document | None:
    """One Document from several windows' blocks, in document order."""
    docs = [d for d in docs if d is not None]
    if not docs:
        return None
    blocks = sorted((b for d in docs for b in d.blocks), key=lambda b: (b.page, b.bbox[1]))
    return Document(source=docs[0].source, blocks=blocks,
                    full_text="\n".join(b.text for b in blocks),
                    page_images=docs[0].page_images, chars=docs[0].chars)


def _domain_inputs(pdf_path: Path, win: dict, routed) -> tuple[dict, list | None, list]:
    """Per-domain evidence: ``{domain: (document, scoped_extras)}``.

    Reads each domain from its own section (title-matched slots), furniture
    stripped. ``scoped_extras`` carries the eligibility inclusion/exclusion windows
    and the objectives-table rows. Also returns the schedule-of-activities page
    range, and findings for every slot that was not found.
    """
    findings: list[Finding] = []
    clean = {d: strip_furniture(w.document) for d, w in win.items()}
    graph = routed.graph if routed else None
    have_graph = graph is not None and bool(graph.sections)

    def slot(domain: str, *names: str, front: int = 0):
        if not have_graph:
            return None
        w = slot_document(clean[domain], graph, *names, front_pages=front)
        if w is None:
            findings.append(Finding(
                FindingKind.SCOPE, Severity.WARNING, domain,
                f"Section slot {'/'.join(names)} not found in the outline; "
                "reading the routed window instead."))
        return w

    meta_w = slot("metadata", "synopsis", front=2)
    design_w = slot("design", "design", "synopsis", "interventions")
    inc_w, exc_w = slot("eligibility", "inclusion"), slot("eligibility", "exclusion")
    obj_w = slot("objectives", "objectives")
    rows = None
    if obj_w is not None:
        from usdm4_assure.extract.objectives_table import read_objectives_table
        rows = read_objectives_table(pdf_path, obj_w.pages) or None
        if rows is None:
            findings.append(Finding(
                FindingKind.SCOPE, Severity.WARNING, "objectives",
                "No objectives/endpoints/estimands table was found on the objectives "
                "pages; falling back to text labels."))
    elig_doc = _merged(inc_w.document if inc_w else None, exc_w.document if exc_w else None)

    inputs = {
        "metadata": (meta_w.document if meta_w else clean["metadata"], None),
        "design": (design_w.document if design_w else clean["design"], None),
        "eligibility": (elig_doc or clean["eligibility"],
                        {"inclusion_doc": inc_w.document if inc_w else None,
                         "exclusion_doc": exc_w.document if exc_w else None}
                        if (inc_w or exc_w) else None),
        "objectives": (obj_w.document if obj_w else clean["objectives"], {"rows": rows}),
    }
    soa_w = slot_document(clean["design"], graph, "soa") if have_graph else None
    if have_graph and soa_w is None:
        findings.append(Finding(
            FindingKind.SCOPE, Severity.WARNING, "soa",
            "No schedule-of-activities section found in the outline; the table finder "
            "will search the whole document."))
    return inputs, (soa_w.pages if soa_w else None), findings


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
