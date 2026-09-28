"""Post-edit-distance telemetry and edit -> label export (task 5.2).

**Post-edit distance.** For a certified run, per field: the normalized
character edit distance between the pipeline's original ``EXTRACTION`` value
and that field's value *as of certification* (its latest record at or before
the ``CERTIFY`` timestamp — a later edit made after certifying doesn't count
against this certified state). ``0.0`` = the pipeline's value needed no
change; ``1.0`` = effectively rewritten. This is the measurable "how much did
review actually cost" number DESIGN.md §5 lists among the operational metrics.

**Edit -> label export.** A reviewer's corrected value is real signal — it is
closer to ground truth than the pipeline's own guess — but it does not carry
the same provenance as a hand-curated ground-truth label (task 4.1), so it
never touches ``data/labels/fields/`` (frozen). Edited fields from a certified
run are written to ``data/labels/edits/<study_id>.jsonl`` instead: a separate,
explicitly-not-frozen, always-regenerable directory, labelled
``review_edit:<source>`` so its provenance is visible wherever it is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from usdm4_assure.contracts_audit import AuditEvent, AuditRecord
from usdm4_assure.eval.labels import FIELD_TYPES, FieldLabel, write_labels

REPO_ROOT = Path(__file__).resolve().parents[3]
EDITS_DIR = REPO_ROOT / "data" / "labels" / "edits"


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance, character-level, iterative (O(len(a)*len(b)) time, O(len(b)) space)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[len(b)]


def normalized_edit_distance(a: str | None, b: str | None) -> float:
    """``edit_distance / max(len(a), len(b))``, in [0, 1]. Two empty/``None`` values are 0.0."""
    a, b = a or "", b or ""
    denom = max(len(a), len(b))
    return 0.0 if denom == 0 else edit_distance(a, b) / denom


@dataclass(frozen=True)
class FieldEditDistance:
    domain: str
    field: str
    original_value: str | None
    certified_value: str | None
    distance: float
    edited: bool    # whether at least one REVIEW_EDIT record exists for this field


def certification_time(records: list[AuditRecord]) -> str | None:
    """The latest ``CERTIFY`` record's timestamp, or ``None`` if the run isn't certified."""
    certs = [r for r in records if r.event is AuditEvent.CERTIFY]
    return certs[-1].timestamp_utc if certs else None


def _certification_index(records: list[AuditRecord]) -> int | None:
    """Position of the latest ``CERTIFY`` record in ``records``, or ``None``.

    Cuts on insertion order (``AuditStore.read_all()``'s rowid order), not on
    ``timestamp_utc`` string comparison: two records appended microseconds
    apart can carry an identical timestamp on a coarse system clock, and a
    string-timestamp cutoff would then wrongly let a later edit count as "as
    of certification". The store's own row order has no such ambiguity.
    """
    idx = [i for i, r in enumerate(records) if r.event is AuditEvent.CERTIFY]
    return idx[-1] if idx else None


def per_field_edit_distance(records: list[AuditRecord]) -> list[FieldEditDistance]:
    """Post-edit distance for every field, as of this run's certification.

    Raises:
        ValueError: the run has no ``CERTIFY`` record — there is no "as of
            certification" state to measure against.
    """
    cert_idx = _certification_index(records)
    if cert_idx is None:
        raise ValueError("run is not certified; nothing to report post-edit distance for")

    by_field: dict[tuple[str, str], list[tuple[int, AuditRecord]]] = {}
    for i, r in enumerate(records):
        if r.field is not None:
            by_field.setdefault((r.domain, r.field), []).append((i, r))

    out = []
    for (domain, field), indexed in sorted(by_field.items()):
        original = indexed[0][1].value                     # oldest: the original extraction
        eligible = [r for i, r in indexed if i <= cert_idx]
        current = eligible[-1] if eligible else None
        edited = any(r.event is AuditEvent.REVIEW_EDIT for _, r in indexed)
        out.append(FieldEditDistance(
            domain=domain, field=field, original_value=original,
            certified_value=current.value if current else None,
            distance=normalized_edit_distance(original, current.value if current else None),
            edited=edited))
    return out


@dataclass(frozen=True)
class DistanceSummary:
    n_fields: int
    n_edited: int
    mean_distance: float | None       # over all fields
    mean_distance_of_edited: float | None  # over edited fields only


def summarize_distances(distances: list[FieldEditDistance]) -> DistanceSummary:
    edited = [d for d in distances if d.edited]
    return DistanceSummary(
        n_fields=len(distances), n_edited=len(edited),
        mean_distance=(sum(d.distance for d in distances) / len(distances)
                      if distances else None),
        mean_distance_of_edited=(sum(d.distance for d in edited) / len(edited)
                                 if edited else None))


def export_edits(source_sha256: str, records: list[AuditRecord], study_id: str | None = None,
                 out_dir: Path = EDITS_DIR) -> Path | None:
    """Write every reviewer-edited field's certified value to ``data/labels/edits/``.

    Only fields with at least one ``REVIEW_EDIT`` record are exported — a
    field the pipeline got right and nobody touched carries no additional
    signal over the frozen labels. Returns ``None`` (writes nothing) if the
    run is not certified or no field was edited.

    Unlike ``data/labels/fields/`` this directory is not frozen: re-exporting
    a study after a later certification overwrites its file, which is the
    point — it tracks the *current* certified state, not a historical one.
    """
    try:
        distances = per_field_edit_distance(records)
    except ValueError:
        return None
    edited = [d for d in distances if d.edited and d.certified_value]
    if not edited:
        return None

    study_id = study_id or source_sha256[:12]
    labelled_at = datetime.now(UTC).isoformat(timespec="seconds")
    labeler = f"review_edit:{source_sha256[:12]}"
    labels = [FieldLabel(study_id=study_id, domain=d.domain, field=d.field,
                         value=d.certified_value,
                         field_type=FIELD_TYPES.get((d.domain, d.field), "scalar"),
                         labeler=labeler, labeled_at=labelled_at) for d in edited]
    return write_labels(out_dir / f"{study_id}.jsonl", labels, force=True)
