"""Estimands -> the usdm4 assembler's ``ObjectivesInput`` (task 6.1).

The assembler links an estimand to its endpoint and treatments *by name*
(``EstimandInput.endpoint_name`` must match a named endpoint; its
``treatment_names`` must match declared interventions), and rejects the
whole input if a reference dangles. So linking happens here, deterministically,
before assembly: every endpoint gets a stable name, each estimand's variable is
matched to the most similar extracted endpoint, and its treatment text to
intervention names. An estimand that cannot be linked is left out of the
assembled study and reported — never attached to a guessed endpoint.
"""
from __future__ import annotations

import copy

from usdm4_assure.contracts import Finding, FindingKind, Severity
from usdm4_assure.extract.estimands import DOMAIN, EstimandsExtract, token_jaccard

LINK_THRESHOLD = 0.3        # variable <-> endpoint text, token Jaccard
TREATMENT_THRESHOLD = 0.5   # intervention name <-> treatment text


def _finding(index: int, severity: Severity, message: str) -> Finding:
    return Finding(FindingKind.COMPLETENESS, severity, DOMAIN, message,
                   field=f"estimand{index}")


def _named_endpoints(block: dict) -> list[dict]:
    """Give every endpoint a stable ``END-n`` name (keeping any existing one)."""
    endpoints, n = [], 0
    for objective in block.get("objectives", []):
        for endpoint in objective.get("endpoints", []):
            n += 1
            if not endpoint.get("name"):
                endpoint["name"] = f"END-{n}"
            endpoints.append(endpoint)
    return endpoints


def _treatment_names(treatment: str, intervention_names: list[str]) -> list[str]:
    low = treatment.lower()
    return [n for n in intervention_names
            if n and (n.lower() in low or token_jaccard(n, treatment) >= TREATMENT_THRESHOLD)]


def link_estimands(extract: EstimandsExtract, objectives_block: dict,
                   intervention_names: list[str]) -> tuple[dict, list[Finding]]:
    """A copy of ``objectives_block`` with named endpoints and linked estimands.

    Returns:
        ``(block, findings)`` — ``block["estimands"]`` holds one
        ``EstimandInput``-shaped dict per estimand that could be linked.
    """
    block = copy.deepcopy(objectives_block)
    endpoints = _named_endpoints(block)
    linked, findings = [], []
    for est in extract.estimands:
        if not est.usable:
            findings.append(_finding(est.index, Severity.WARNING,
                                     f"{est.name} not assembled: its variable or summary "
                                     "measure is missing or failed grounding."))
            continue
        variable = est.value("variable")
        scored = [(token_jaccard(variable, e.get("text", "")), e) for e in endpoints]
        score, endpoint = max(scored, key=lambda s: s[0], default=(0.0, None))
        if endpoint is None or score < LINK_THRESHOLD:
            findings.append(_finding(est.index, Severity.WARNING,
                                     f"{est.name} not assembled: its variable ('{variable[:80]}') "
                                     "matches no extracted endpoint."))
            continue
        treatment = est.value("treatment") or ""
        treatments = _treatment_names(treatment, intervention_names)
        if treatment and not treatments:
            findings.append(_finding(est.index, Severity.INFO,
                                     f"{est.name}: treatment '{treatment[:80]}' matches no "
                                     "intervention; assembled without intervention links."))
        linked.append({
            "name": f"EST-{est.index}", "label": est.name,
            "summary_measure": est.value("summary_measure"),
            "population_text": est.value("population") or "",
            "treatment_names": treatments, "endpoint_name": endpoint["name"],
            "intercurrent_events": [{"text": i.text, "strategy": i.strategy}
                                    for i in est.intercurrent_events],
        })
    block["estimands"] = linked
    return block, findings
