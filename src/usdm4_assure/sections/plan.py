"""Route plan (task 3.4) — section graph + fingerprint → ported route planner.

Everything upstream of :func:`generate_study_extraction_plan` is ours and
deterministic; the planner itself is the reference extractor's route mapping
(:mod:`usdm4_assure.sections._ported_routes`), used as-is. The plan's hash is
what audit records cite (task 3.5), so it is computed over a canonical JSON
form and is stable across runs and dict orderings.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from usdm4_assure.contracts import Document
from usdm4_assure.llm.base import LLM
from usdm4_assure.sections._ported_routes import generate_study_extraction_plan
from usdm4_assure.sections.fingerprint import fingerprint
from usdm4_assure.sections.graph import SectionGraph, build_graph, classify_residue
from usdm4_assure.sections.models import DomainRoutePlan, StudyExtractionPlan

# Our extraction domains (Shard.domain / AssuredField.domain) → the ported
# planner's route names.
DOMAIN_ROUTES: dict[str, str] = {
    "metadata": "study_header",
    "design": "design_structure",
    "eligibility": "populations_eligibility",
    "objectives": "objectives_endpoints",
    "estimands": "estimands",
    "sites": "organizations_sites",
    "soa": "schedule_activities",
}


@dataclass
class RoutedDocument:
    """Everything routing produced for one document."""
    graph: SectionGraph
    plan: StudyExtractionPlan

    @property
    def plan_hash(self) -> str:
        return plan_hash(self.plan)

    def route_for(self, domain: str) -> DomainRoutePlan | None:
        """The route for one of *our* domains (``None`` if the domain is unrouted)."""
        name = DOMAIN_ROUTES.get(domain)
        return self.plan.domain_routes.get(name) if name else None


def plan_hash(plan: StudyExtractionPlan) -> str:
    canonical = json.dumps(plan.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_plan(doc: Document, pdf_path: str | Path | None = None,
               route_llm: LLM | None = None) -> RoutedDocument:
    """Deterministic graph → (optional ``route``-role residue) → fingerprint → plan."""
    graph = classify_residue(build_graph(doc, pdf_path), route_llm)
    fp = fingerprint(doc, graph)
    pages = max(doc.chars, default=0) or max((b.page for b in doc.blocks), default=0)
    plan = generate_study_extraction_plan(
        fingerprint=fp, graph_summary=graph.summary(page_count=pages).to_dict())
    return RoutedDocument(graph=graph, plan=plan)
