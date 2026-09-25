"""Ground-truth label flattening and the frozen-file contract (task 4.1)."""
from __future__ import annotations

import json

import pytest

from usdm4_assure.eval.labels import (
    FIELD_TYPES,
    FieldLabel,
    flatten_study,
    read_labels,
    write_labels,
)

LABELED_AT = "2026-01-01T00:00:00+00:00"


def _wrapper(**overrides) -> dict:
    version = {
        "versionIdentifier": "1",
        "titles": [{"text": "Official Title Text", "type": {"decode": "Official Study Title"}},
                  {"text": "TBD", "type": {"decode": "Public Study Title"}}],
        "studyIdentifiers": [{"text": "SPONSOR-001", "scopeId": "Organization_1"},
                            {"text": "NCT00000000", "scopeId": "Organization_2"}],
        "organizations": [{"id": "Organization_1", "name": "Acme",
                          "type": {"decode": "Drug Company"}},
                         {"id": "Organization_2", "name": "CT-GOV",
                          "type": {"decode": "Study Registry"}}],
        "eligibilityCriterionItems": [{"id": "Item_1", "text": "<p>Adults aged 18+.</p>"},
                                     {"id": "Item_2", "text": "Pregnant women."}],
        "studyDesigns": [{
            "studyType": {"decode": "Interventional Study"},
            "model": {"decode": "Parallel Study"},
            "studyPhase": {"standardCode": {"decode": "Phase II Trial"}},
            "eligibilityCriteria": [
                {"criterionItemId": "Item_1", "category": {"decode": "Inclusion Criteria"}},
                {"criterionItemId": "Item_2", "category": {"decode": "Exclusion Criteria"}},
            ],
            "population": {
                "plannedAge": {"minValue": {"value": 18.0}, "maxValue": {"value": 65.0}},
                "plannedSex": [{"decode": "Both"}],
            },
            "objectives": [
                {"text": "Primary objective text.", "level": {"decode": "Trial Primary Objective"},
                 "endpoints": [{"text": "Primary endpoint text."}]},
                {"text": "Secondary objective text.", "level": {"decode": "Trial Secondary Objective"},
                 "endpoints": [{"text": "Secondary endpoint text."}]},
            ],
        }],
    }
    version.update(overrides)
    return {"usdmVersion": "4.0.0", "study": {"versions": [version]}}


def test_flatten_reads_every_field():
    labels = {(l.domain, l.field): l.value for l in flatten_study(_wrapper(), "S1")}
    assert labels[("metadata", "studyTitle")] == "Official Title Text"
    assert labels[("metadata", "sponsorName")] == "Acme"
    assert labels[("metadata", "protocolIdentifier")] == "SPONSOR-001"   # sponsor org's id, not NCT
    assert labels[("metadata", "studyPhase")] == "Phase 2"
    assert labels[("design", "studyType")] == "Interventional Study"
    assert labels[("design", "interventionModel")] == "Parallel Study"
    assert labels[("eligibility", "inclusionCriteria")] == "Adults aged 18+."
    assert labels[("eligibility", "exclusionCriteria")] == "Pregnant women."
    assert labels[("eligibility", "plannedMinimumAge")] == "18.0"
    assert labels[("eligibility", "plannedMaximumAge")] == "65.0"
    assert labels[("eligibility", "plannedSex")] == "ALL"
    assert labels[("objectives", "primaryObjective")] == "Primary objective text."
    assert labels[("objectives", "primaryEndpoint")] == "Primary endpoint text."
    assert labels[("objectives", "secondaryObjective")] == "Secondary objective text."
    assert labels[("objectives", "secondaryEndpoint")] == "Secondary endpoint text."
    assert ("metadata", "studyAcronym") not in labels    # "TBD" title is a placeholder, dropped


def test_flatten_sets_field_type_from_the_shared_table():
    labels = flatten_study(_wrapper(), "S1")
    for l in labels:
        assert l.field_type == FIELD_TYPES[(l.domain, l.field)]
        assert l.study_id == "S1" and l.labeler and l.labeled_at


def test_compound_phase():
    w = _wrapper()
    w["study"]["versions"][0]["studyDesigns"][0]["studyPhase"]["standardCode"]["decode"] = \
        "Phase I/II Trial"
    labels = {(l.domain, l.field): l.value for l in flatten_study(w, "S1")}
    assert labels[("metadata", "studyPhase")] == "Phase 1/2"


def test_missing_value_is_simply_absent_not_empty_string():
    w = _wrapper()
    w["study"]["versions"][0]["studyDesigns"][0]["population"]["plannedSex"] = []
    labels = {(l.domain, l.field) for l in flatten_study(w, "S1")}
    assert ("eligibility", "plannedSex") not in labels


def test_write_refuses_to_overwrite_without_force(tmp_path):
    path = tmp_path / "S1.jsonl"
    labels = [FieldLabel("S1", "metadata", "studyPhase", "Phase 2", "scalar", "t", LABELED_AT)]
    write_labels(path, labels)
    with pytest.raises(FileExistsError):
        write_labels(path, labels)
    write_labels(path, labels, force=True)   # deliberate overwrite still works


def test_write_read_roundtrip_is_sorted_and_jsonl(tmp_path):
    path = tmp_path / "S1.jsonl"
    labels = [FieldLabel("S1", "objectives", "primaryObjective", "x", "long_text", "t", LABELED_AT),
             FieldLabel("S1", "design", "studyType", "y", "scalar", "t", LABELED_AT)]
    write_labels(path, labels)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(ln)["domain"] for ln in lines] == ["design", "objectives"]
    assert read_labels(path) == sorted(labels, key=lambda l: (l.domain, l.field))


def test_read_missing_file_returns_empty(tmp_path):
    assert read_labels(tmp_path / "absent.jsonl") == []
