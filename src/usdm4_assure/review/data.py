"""Read-side queries over the audit store for the review UI (task 5.1).

Kept separate from :mod:`usdm4_assure.review.app` so the FastAPI layer stays
thin routing glue: every function here takes/returns plain data (records,
dataclasses), nothing web-framework-specific, and is unit-testable without an
HTTP client.

The central idea, and the one thing worth explaining once: the audit store is
append-only, so a field's **current** value is not a column anywhere — it is
simply the *last* record written for that ``(domain, field)`` key, whatever
event wrote it. A reviewer's edit is a new record with the same key, so it
naturally becomes "current" the moment it's appended; nothing is ever
overwritten to make that true.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from usdm4_assure.audit.store import AuditStore, audit_dir, audit_path, read_source_pointer
from usdm4_assure.contracts import Decision
from usdm4_assure.contracts_audit import AuditEvent, AuditRecord

# Risk order for sorting: worst-first, so a reviewer's attention goes where it
# is needed. A decision this UI has never seen (defensive) sorts as REVIEW,
# not last — an unknown state should not be mistaken for a safe one.
_DECISION_RISK = {Decision.BLOCK: 0, Decision.REVIEW: 1, Decision.AUTO_ACCEPT: 2}


@dataclass(frozen=True)
class SourceSummary:
    """One row of the review UI's home page."""
    source_sha256: str
    pdf_path: str | None
    n_records: int
    n_fields: int
    run_ids: list[str]
    decision_summary: dict[str, int]
    certified: bool


def current_fields(records: list[AuditRecord]) -> dict[tuple[str, str], AuditRecord]:
    """The latest record for every ``(domain, field)`` that has one.

    ``records`` must be oldest-first (``AuditStore.read_all()``'s order), so
    the last occurrence of a key is that field's current state. Certification
    and calibration records (``field is None``) describe the run, not a
    field, and are excluded.
    """
    current: dict[tuple[str, str], AuditRecord] = {}
    for rec in records:
        if rec.field is not None:
            current[(rec.domain, rec.field)] = rec
    return current


def risk_sorted(fields: list[AuditRecord]) -> list[AuditRecord]:
    """Worst-first: BLOCK, then REVIEW, then AUTO_ACCEPT; ties by confidence ascending
    (lower confidence = more likely to need a human look, so it sorts first)."""
    def key(rec: AuditRecord) -> tuple[int, float]:
        risk = _DECISION_RISK.get(rec.decision, 1)
        confidence = rec.confidence if rec.confidence is not None else 0.0
        return (risk, confidence)
    return sorted(fields, key=key)


def summarize_source(source_sha256: str, records: list[AuditRecord],
                     base_dir: str | Path | None = None) -> SourceSummary:
    current = current_fields(records)
    decision_summary = {d.value: 0 for d in Decision}
    for rec in current.values():
        if rec.decision is not None:
            decision_summary[rec.decision.value] += 1
    ptr = read_source_pointer(source_sha256, base_dir)
    return SourceSummary(
        source_sha256=source_sha256, pdf_path=ptr["pdf_path"] if ptr else None,
        n_records=len(records), n_fields=len(current),
        run_ids=sorted({r.run_id for r in records}), decision_summary=decision_summary,
        certified=any(r.event is AuditEvent.CERTIFY for r in records))


def list_sources(base_dir: str | Path | None = None) -> list[SourceSummary]:
    """One :class:`SourceSummary` per audit database under ``base_dir``.

    ``base_dir`` defaults to the configured audit directory (``USDM4_AUDIT_DIR``
    or ``data/audit``). Returns ``[]`` (not an error) when it does not exist.
    """
    directory = audit_dir(base_dir)
    if not directory.is_dir():
        return []
    out = []
    for db in sorted(directory.glob("*.sqlite")):
        store = AuditStore(path=db)
        records = store.read_all()
        store.close()
        if records:
            out.append(summarize_source(db.stem, records, base_dir))
    return out


def open_store(source_sha256: str, base_dir: str | Path | None = None) -> AuditStore:
    return AuditStore(path=audit_path(source_sha256, base_dir))
