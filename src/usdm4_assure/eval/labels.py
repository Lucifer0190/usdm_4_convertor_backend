"""Frozen ground-truth field labels (task 4.1, PLAN.md §8.5).

usdm_data ships a handful of studies as *completed, pre-assembled* USDM 4.0
wrapper JSON (see :mod:`usdm4_assure.eval.corpus`'s docstring and
``spikes/measure_assembler.py``) alongside their source protocol PDF. Only
four are both USDM v4.0.x and a real (non-synthetic) protocol: Alexion,
CDISC Pilot, Eli Lilly (NCT03421379), Sanofi. :func:`flatten_study` turns one
of those wrapper JSONs into one :class:`FieldLabel` per field our extractors
actually populate (``extract.metadata.FIELDS``, ``DESIGN_FIELDS``,
``ELIGIBILITY_FIELDS``, ``OBJECTIVES_FIELDS``) — the same (domain, field)
grain as :class:`~usdm4_assure.contracts.AssuredField`, so a label scores
directly against a pipeline run's output.

**Frozen.** :func:`write_labels` refuses to overwrite an existing file unless
``force=True``. A label file, once committed, is ground truth for every
future run; regenerating it silently would let a scorer's target quietly
drift. These four studies are also **held out**: PLAN.md's model-selection and
routing work (Phases 0-3) must not be tuned by looking at them — they exist
only to measure, starting with :func:`usdm4_assure.eval.score.score_fields`
here and the Phase 4 confidence model that reads ``features.parquet`` later.

A label with no value in the source JSON (an empty acronym, USDM has no
concept for a field at all) is simply not emitted — absence is not a "found
nothing" label, it is "this field can't be checked here".
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

FieldType = Literal["scalar", "long_text", "number"]

# (domain, field) -> field_type, matching AssuredField's (domain, field) grain
# and extract.shards.Shard field lists.
FIELD_TYPES: dict[tuple[str, str], FieldType] = {
    ("metadata", "studyTitle"): "long_text",
    ("metadata", "studyAcronym"): "scalar",
    ("metadata", "sponsorName"): "scalar",
    ("metadata", "studyPhase"): "scalar",
    ("metadata", "protocolIdentifier"): "scalar",
    ("metadata", "studyVersionIdentifier"): "scalar",
    ("design", "studyType"): "scalar",
    ("design", "interventionModel"): "scalar",
    ("eligibility", "inclusionCriteria"): "long_text",
    ("eligibility", "exclusionCriteria"): "long_text",
    ("eligibility", "plannedMinimumAge"): "number",
    ("eligibility", "plannedMaximumAge"): "number",
    ("eligibility", "plannedSex"): "scalar",
    ("objectives", "primaryObjective"): "long_text",
    ("objectives", "primaryEndpoint"): "long_text",
    ("objectives", "secondaryObjective"): "long_text",
    ("objectives", "secondaryEndpoint"): "long_text",
}

_ROMAN_PHASE = {"0": "0", "i": "1", "ii": "2", "iii": "3", "iv": "4"}
_SEX_DECODE = {"both": "ALL", "male": "MALE", "female": "FEMALE"}


@dataclass(frozen=True)
class FieldLabel:
    """One frozen ground-truth value for one (study, domain, field)."""
    study_id: str
    domain: str
    field: str
    value: str
    field_type: FieldType
    labeler: str
    labeled_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class _TextExtractor(HTMLParser):
    """Strips HTML tags (usdm:tag elements included) from a criterion item's text."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _strip_html(html: str) -> str:
    p = _TextExtractor()
    p.feed(html or "")
    return re.sub(r"\s+", " ", "".join(p.parts)).strip()


def _decode(coded: dict | None) -> str | None:
    """The human-readable ``decode`` of a USDM ``Code``/``AliasCode``, or ``None``."""
    if not isinstance(coded, dict):
        return None
    if "decode" in coded:
        return coded.get("decode") or None
    return _decode(coded.get("standardCode"))


def _org_by_type(orgs: list[dict], type_decode: str) -> dict | None:
    return next((o for o in orgs if _decode(o.get("type")) == type_decode), None)


def _title(titles: list[dict], type_decode: str) -> str | None:
    return next((t.get("text") for t in titles
                if _decode(t.get("type")) == type_decode and t.get("text")
                and t["text"] != "TBD"), None)


def _phase(decode: str | None) -> str | None:
    """"Phase II Trial" -> "Phase 2"; "Phase I/II Trial" -> "Phase 1/2".

    Unrecognised forms pass through unchanged.
    """
    if not decode:
        return None
    m = re.search(r"phase\s+((?:0|i{1,3}v?|iv)(?:\s*/\s*(?:0|i{1,3}v?|iv))*)\b",
                  decode, re.IGNORECASE)
    if not m:
        return decode
    parts = [_ROMAN_PHASE.get(p.lower(), p) for p in re.split(r"\s*/\s*", m.group(1))]
    return f"Phase {'/'.join(parts)}"


def _sex(codes: list[dict] | None) -> str | None:
    decodes = {_decode(c) for c in (codes or [])}
    decodes.discard(None)
    if len(decodes) != 1:
        return None
    return _SEX_DECODE.get(next(iter(decodes)).lower())


def _eligibility_text(design: dict, version: dict, category_decode: str) -> str | None:
    items_by_id = {i["id"]: i for i in version.get("eligibilityCriterionItems") or []}
    texts = [
        _strip_html(items_by_id[c["criterionItemId"]]["text"])
        for c in design.get("eligibilityCriteria") or []
        if _decode(c.get("category")) == category_decode and c.get("criterionItemId") in items_by_id
    ]
    joined = " ".join(t for t in texts if t)
    return joined or None


def _objectives(design: dict, level_decode: str, want: Literal["objective", "endpoint"]
                ) -> str | None:
    objs = [o for o in design.get("objectives") or [] if _decode(o.get("level")) == level_decode]
    if not objs:
        return None
    if want == "objective":
        text = objs[0].get("text")
        return _strip_html(text) or None if text else None
    endpoints = objs[0].get("endpoints") or []
    text = endpoints[0].get("text") if endpoints else None
    return _strip_html(text) or None if text else None


def flatten_study(wrapper: dict, study_id: str, labeler: str = "usdm_data",
                  labeled_at: str | None = None) -> list[FieldLabel]:
    """Every (domain, field) label :func:`flatten_study` can read out of ``wrapper``.

    Args:
        wrapper: A USDM 4.0 wrapper dict (``{"study": {...}, "usdmVersion": ...}``),
            as shipped by usdm_data.
        study_id: The corpus study id (matches :class:`~usdm4_assure.eval.corpus.Study`).
        labeler: Provenance tag recorded on every label (default: the corpus source).
        labeled_at: ISO-8601 UTC timestamp; defaults to now.
    """
    labeled_at = labeled_at or datetime.now(UTC).isoformat()
    version = (wrapper.get("study") or {}).get("versions", [{}])[0]
    design = (version.get("studyDesigns") or [{}])[0]
    orgs = version.get("organizations") or []
    sponsor = _org_by_type(orgs, "Drug Company")

    raw: dict[tuple[str, str], object] = {
        ("metadata", "studyTitle"): _title(version.get("titles") or [], "Official Study Title"),
        ("metadata", "studyAcronym"): _title(version.get("titles") or [], "Study Acronym"),
        ("metadata", "sponsorName"): sponsor.get("name") if sponsor else None,
        ("metadata", "studyPhase"): _phase(_decode(design.get("studyPhase"))),
        ("metadata", "protocolIdentifier"): next(
            (i.get("text") for i in version.get("studyIdentifiers") or []
             if sponsor and i.get("scopeId") == sponsor.get("id")), None),
        ("metadata", "studyVersionIdentifier"): version.get("versionIdentifier"),
        ("design", "studyType"): _decode(design.get("studyType")),
        ("design", "interventionModel"): _decode(design.get("model")),
        ("eligibility", "inclusionCriteria"): _eligibility_text(design, version, "Inclusion Criteria"),
        ("eligibility", "exclusionCriteria"): _eligibility_text(design, version, "Exclusion Criteria"),
        ("objectives", "primaryObjective"): _objectives(design, "Trial Primary Objective", "objective"),
        ("objectives", "primaryEndpoint"): _objectives(design, "Trial Primary Objective", "endpoint"),
        ("objectives", "secondaryObjective"): _objectives(design, "Trial Secondary Objective", "objective"),
        ("objectives", "secondaryEndpoint"): _objectives(design, "Trial Secondary Objective", "endpoint"),
    }
    population = design.get("population") or {}
    planned_age = population.get("plannedAge") or {}
    raw[("eligibility", "plannedMinimumAge")] = (planned_age.get("minValue") or {}).get("value")
    raw[("eligibility", "plannedMaximumAge")] = (planned_age.get("maxValue") or {}).get("value")
    raw[("eligibility", "plannedSex")] = _sex(population.get("plannedSex"))

    labels = []
    for (domain, field), value in raw.items():
        if value is None or value == "":
            continue
        labels.append(FieldLabel(study_id=study_id, domain=domain, field=field,
                                 value=str(value), field_type=FIELD_TYPES[(domain, field)],
                                 labeler=labeler, labeled_at=labeled_at))
    return labels


def write_labels(path: str | Path, labels: list[FieldLabel], force: bool = False) -> Path:
    """Write ``labels`` as JSON Lines, one label per line, sorted for determinism.

    Refuses to overwrite an existing file unless ``force=True`` — see the
    module docstring's "Frozen" note.
    """
    path = Path(path)
    if path.exists() and not force:
        raise FileExistsError(
            f"{path} already exists and labels are frozen; pass force=True to overwrite "
            "deliberately (and note why in the commit that does it).")
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(labels, key=lambda l: (l.domain, l.field))
    path.write_text("\n".join(json.dumps(l.to_dict(), sort_keys=True) for l in ordered) + "\n",
                    encoding="utf-8")
    return path


def read_labels(path: str | Path) -> list[FieldLabel]:
    """Read a label file written by :func:`write_labels`."""
    path = Path(path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [FieldLabel(**json.loads(line)) for line in lines if line.strip()]
