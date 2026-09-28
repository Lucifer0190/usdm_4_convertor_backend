"""Bridges pipeline output to the audit store — one record per field decision.

Keeps :mod:`usdm4_assure.pipeline` from having to know the shape of
:class:`~usdm4_assure.contracts_audit.AuditRecord`; it just calls
:func:`write_field_decision` (or :func:`write_run`) once the Assurance layer
has produced its :class:`~usdm4_assure.contracts.AssuredField` list.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from usdm4_assure.audit.store import AuditStore
from usdm4_assure.contracts import AssuredField, Decision, GroundedCandidate, Method
from usdm4_assure.contracts_audit import AuditEvent, AuditRecord

# A reviewer edit or certification applies across every domain, not one —
# AuditRecord.domain has no default, so this documents what a wildcard means
# rather than overloading a real domain name like "metadata".
ALL_DOMAINS = "*"

if TYPE_CHECKING:
    from usdm4_assure.assure.conformal import ConformalBound


def _bound_summary(bound: ConformalBound) -> dict:
    """What a field-level record needs to cite the bound it was triaged under."""
    return {"alpha": bound.alpha, "delta": bound.delta, "threshold": bound.threshold,
            "model_hash": bound.model_hash, "calibration_hash": bound.calibration_hash,
            "refused_reason": bound.refused_reason}


def _winning_candidate(assured: AssuredField) -> GroundedCandidate | None:
    """The grounded candidate that produced ``assured.value``, if any.

    Deterministic-only fields (no ``GroundedCandidate`` among their sources, or
    a value with no matching candidate) simply carry no model/prompt provenance
    — that is a correct, expected state, not an error.
    """
    for c in assured.candidates:
        if isinstance(c, GroundedCandidate) and c.value == assured.value:
            return c
    return None


def write_field_decision(store: AuditStore, *, run_id: str, source_sha256: str,
                          domain: str, assured: AssuredField,
                          pipeline_version: str | None = None,
                          retrieval_config: dict | None = None,
                          bound: ConformalBound | None = None) -> AuditRecord:
    """Append one :class:`AuditRecord` for a single :class:`AssuredField`.

    Args:
        store: The open audit store for this source PDF.
        run_id: Identifies this pipeline run (groups every record it wrote).
        source_sha256: The source PDF's sha256.
        domain: Extraction domain (``"metadata"``, ``"design"``, ...).
        assured: The field as decided by the Assurance layer.
        pipeline_version: Optional version/commit tag of the running pipeline.
        retrieval_config: How the field's evidence was selected — for a
            routed run, the domain's ``EvidenceWindow.retrieval_config()``
            (route name + route-plan hash + what was filtered out).
        bound: The conformal bound the field was triaged under (task 4.3), as
            it applied to this protocol. Its threshold fills the record's
            ``threshold`` column; its model and calibration-set hashes go into
            ``verification["conformal"]`` so the decision is reproducible.

    Returns:
        The :class:`AuditRecord` that was appended.
    """
    winner = _winning_candidate(assured)
    quote = assured.quote or (winner.quote if winner else None)
    record = AuditRecord(
        run_id=run_id, event=AuditEvent.EXTRACTION, source_sha256=source_sha256,
        domain=domain, field=assured.field, pipeline_version=pipeline_version,
        value=assured.value, method=(winner.method if winner else None),
        decision=assured.decision, confidence=assured.confidence,
        model_id=(winner.model_id if winner else None),
        prompt_hash=(winner.prompt_hash if winner else None),
        retrieval_config=retrieval_config,
        threshold=(bound.threshold if bound else None),
        verification=({"conformal": _bound_summary(bound)} if bound else None),
    ).with_quote(quote)
    store.append(record)
    return record


def write_run(store: AuditStore, *, run_id: str, source_sha256: str, domain: str,
              assured_fields: list[AssuredField],
              pipeline_version: str | None = None,
              retrieval_config: dict | None = None,
              bound: ConformalBound | None = None) -> list[AuditRecord]:
    """Append one record per field in ``assured_fields``; returns them in order."""
    return [
        write_field_decision(store, run_id=run_id, source_sha256=source_sha256,
                             domain=domain, assured=a, pipeline_version=pipeline_version,
                             retrieval_config=retrieval_config, bound=bound)
        for a in assured_fields
    ]


def write_calibration(store: AuditStore, *, run_id: str, source_sha256: str,
                      bound: ConformalBound, model: dict | None = None,
                      pipeline_version: str | None = None) -> AuditRecord:
    """Append the run-level record of which confidence model and bound were in force.

    One per run, alongside its field records: the full bound (alpha, delta,
    threshold, calibration-set size and hash, coverage, the Clopper-Pearson
    upper bound, strata, or the refusal reason) and, if given, the model's
    serialised parameters, so the auto-accept decision can be reproduced and
    defended from the audit store alone.
    """
    verification: dict = {"conformal": bound.to_dict()}
    if model is not None:
        verification["confidence_model"] = model
    record = AuditRecord(
        run_id=run_id, event=AuditEvent.CALIBRATION, source_sha256=source_sha256,
        domain="assure", field=None, pipeline_version=pipeline_version,
        threshold=bound.threshold, verification=verification)
    store.append(record)
    return record


def write_review_edit(store: AuditStore, *, run_id: str, source_sha256: str, domain: str,
                      field: str, value: str, prior_value: str | None,
                      reviewer_id: str, reason_for_change: str) -> AuditRecord:
    """Append the record of a reviewer changing (or confirming) one field's value.

    A human explicitly supplying a value is, by definition, an accepted one —
    ``decision`` is always ``AUTO_ACCEPT`` and ``method`` is ``HUMAN``, at
    ``confidence=1.0`` (a human decision is not a probabilistic score). The
    prior value is whatever the reviewer saw on screen when they edited it —
    the caller (the review UI) is responsible for passing the *current* value,
    not necessarily the original extraction's.
    """
    record = AuditRecord(
        run_id=run_id, event=AuditEvent.REVIEW_EDIT, source_sha256=source_sha256,
        domain=domain, field=field, value=value, method=Method.HUMAN,
        decision=Decision.AUTO_ACCEPT, confidence=1.0, reviewer_id=reviewer_id,
        prior_value=prior_value, reason_for_change=reason_for_change)
    store.append(record)
    return record


def write_certification(store: AuditStore, *, run_id: str, source_sha256: str,
                        reviewer_id: str, signature_meaning: str) -> AuditRecord:
    """Append the record of a reviewer signing off the run.

    One record, ``domain=ALL_DOMAINS`` — certification is a statement about
    the whole run's field set, not one field.
    """
    record = AuditRecord(
        run_id=run_id, event=AuditEvent.CERTIFY, source_sha256=source_sha256,
        domain=ALL_DOMAINS, field=None, reviewer_id=reviewer_id,
        signature_meaning=signature_meaning)
    store.append(record)
    return record
