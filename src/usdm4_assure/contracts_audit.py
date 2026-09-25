"""The 21 CFR Part 11 audit record — one immutable row per field decision.

DESIGN.md L9: *"Cheap to design in; brutal to retrofit."* Every field the pipeline
emits, every reviewer edit and every certification writes exactly one of these to
an append-only store (Phase 1.4). Nothing here is ever updated in place: a change
of mind is a *new* record whose ``prior_value`` / ``reason_for_change`` point back.

The record is deliberately flat and JSON-friendly so it maps 1:1 onto a SQLite row
and onto a review-UI table without an ORM.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import UTC, datetime
from enum import Enum

from usdm4_assure.contracts import BBox, Decision, Method, Quote, VerifyPass


class AuditEvent(str, Enum):
    """Why the record exists."""
    EXTRACTION = "extraction"    # the pipeline decided a value
    REVIEW_EDIT = "review_edit"  # a reviewer changed / confirmed a value
    CERTIFY = "certify"          # a reviewer signed off the run (signature meaning set)
    CALIBRATION = "calibration"  # the confidence model + conformal bound in force for a run


def utc_now() -> str:
    """ISO-8601 UTC timestamp with explicit offset and microsecond precision."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


def new_record_id() -> str:
    return uuid.uuid4().hex


# Columns that hold structured data; serialised as JSON text in a flat row.
_JSON_FIELDS = ("bbox", "retrieval_config", "verification")


@dataclass(frozen=True)
class AuditRecord:
    """One field-level decision, with everything needed to reproduce and defend it.

    Grouped as DESIGN.md L9 lists them. Optional fields default to ``None`` so a
    deterministic extraction (no model, no prompt) and a certification (no field)
    both fit the same row shape.

    Identity / context
        record_id, run_id, event, source_sha256, pipeline_version, timestamp_utc
    What was decided
        domain, field, value, method, decision, confidence, threshold
    How the model was called (LLM/vision methods only)
        model_id, model_version, prompt_hash, temperature, seed, retrieval_config
    Where it came from (grounding)
        page, char_start, char_end, bbox, quote_text, verify_pass, verification
    Who / why (review and certification)
        reviewer_id, prior_value, reason_for_change, signature_meaning
    """
    # identity / context
    run_id: str
    event: AuditEvent
    source_sha256: str
    domain: str
    field: str | None
    record_id: str = field(default_factory=new_record_id)
    timestamp_utc: str = field(default_factory=utc_now)
    pipeline_version: str | None = None

    # what was decided
    value: str | None = None
    method: Method | None = None
    decision: Decision | None = None
    confidence: float | None = None
    threshold: float | None = None       # auto-accept threshold in force (Phase 4 conformal)

    # how the model was called
    model_id: str | None = None          # OpenRouter slug
    model_version: str | None = None     # provider-reported version/build, if exposed
    prompt_hash: str | None = None
    temperature: float | None = None
    seed: int | None = None
    retrieval_config: dict | None = None  # shard id, window/page selection, route-plan hash

    # where it came from
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    bbox: BBox | None = None
    quote_text: str | None = None
    verify_pass: VerifyPass | None = None
    verification: dict | None = None     # e.g. {"nli": "supported", "agreement": 0.9}

    # who / why
    reviewer_id: str | None = None
    prior_value: str | None = None
    reason_for_change: str | None = None
    signature_meaning: str | None = None  # e.g. "Reviewed and approved for submission"

    # ------------------------------------------------------------------ #
    # Construction helpers
    # ------------------------------------------------------------------ #
    def with_quote(self, quote: Quote | None) -> AuditRecord:
        """Copy with the grounding columns filled from ``quote``."""
        if quote is None:
            return self
        return replace_fields(self, page=quote.page, char_start=quote.char_start,
                              char_end=quote.char_end, bbox=quote.bbox,
                              quote_text=quote.text, verify_pass=quote.verify_pass)

    # ------------------------------------------------------------------ #
    # Flat-row (de)serialisation for the SQLite store and the review UI
    # ------------------------------------------------------------------ #
    def to_row(self) -> dict:
        """Flat ``{column: scalar}`` dict; enums → values, structured cols → JSON text."""
        row = asdict(self)
        for k, v in row.items():
            if isinstance(v, Enum):
                row[k] = v.value
        for k in _JSON_FIELDS:
            if row[k] is not None:
                row[k] = json.dumps(row[k], default=list)
        return row

    @classmethod
    def from_row(cls, row: dict) -> AuditRecord:
        """Inverse of :meth:`to_row`. Unknown columns are ignored."""
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in row.items() if k in known}
        for k in _JSON_FIELDS:
            if isinstance(data.get(k), str):
                data[k] = json.loads(data[k])
        if data.get("bbox") is not None:
            data["bbox"] = tuple(data["bbox"])
        data["event"] = AuditEvent(data["event"])
        for k, enum_cls in (("method", Method), ("decision", Decision),
                            ("verify_pass", VerifyPass)):
            if data.get(k) is not None:
                data[k] = enum_cls(data[k])
        return cls(**data)

    @classmethod
    def columns(cls) -> list[str]:
        """Column names in declaration order — the store's schema follows this."""
        return [f.name for f in fields(cls)]


def replace_fields(rec: AuditRecord, **changes) -> AuditRecord:
    """``dataclasses.replace`` for a frozen record, kept local so the intent is
    visible at call sites: it *creates a new record*, it never edits one."""
    return replace(rec, **changes)
