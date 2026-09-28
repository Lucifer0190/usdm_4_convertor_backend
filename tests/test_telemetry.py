"""Post-edit-distance telemetry and edit -> label export (task 5.2)."""
from __future__ import annotations

import pytest

from usdm4_assure.audit.store import AuditStore
from usdm4_assure.audit.writer import write_certification, write_field_decision, write_review_edit
from usdm4_assure.contracts import AssuredField, Decision
from usdm4_assure.eval.labels import read_labels
from usdm4_assure.review.telemetry import (
    FieldEditDistance,
    certification_time,
    edit_distance,
    export_edits,
    normalized_edit_distance,
    per_field_edit_distance,
    summarize_distances,
)

SHA = "cd" * 32


def _store(tmp_path) -> AuditStore:
    return AuditStore(path=tmp_path / "run.sqlite")


def _extraction(store, domain, field, value, decision=Decision.REVIEW):
    assured = AssuredField(field, value, [], False, 1, "partial", 0.5, decision, domain=domain)
    return write_field_decision(store, run_id="run1", source_sha256=SHA, domain=domain,
                                assured=assured)


# --- edit distance hand cases ------------------------------------------------- #
def test_edit_distance_hand_values():
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("abc", "abc") == 0
    assert edit_distance("", "abc") == 3 and edit_distance("abc", "") == 3


def test_normalized_edit_distance_bounds():
    assert normalized_edit_distance("abc", "abc") == 0.0
    assert normalized_edit_distance("abc", "xyz") == 1.0
    assert normalized_edit_distance(None, None) == 0.0
    assert normalized_edit_distance("", "") == 0.0
    assert 0.0 < normalized_edit_distance("Acme", "Acme Corp") < 1.0


# --- per_field_edit_distance -------------------------------------------------- #
def test_uncertified_run_raises(tmp_path):
    store = _store(tmp_path)
    _extraction(store, "metadata", "sponsorName", "Acme")
    with pytest.raises(ValueError, match="not certified"):
        per_field_edit_distance(store.read_all())


def test_distance_zero_when_no_edit(tmp_path):
    store = _store(tmp_path)
    _extraction(store, "metadata", "sponsorName", "Acme", Decision.AUTO_ACCEPT)
    write_certification(store, run_id="r1", source_sha256=SHA, reviewer_id="jdoe",
                        signature_meaning="ok")
    dists = per_field_edit_distance(store.read_all())
    assert len(dists) == 1
    d = dists[0]
    assert d.edited is False and d.distance == 0.0
    assert d.original_value == d.certified_value == "Acme"


def test_distance_reflects_the_edit(tmp_path):
    store = _store(tmp_path)
    _extraction(store, "metadata", "sponsorName", "Acme")
    write_review_edit(store, run_id="review", source_sha256=SHA, domain="metadata",
                      field="sponsorName", value="Acme Corp", prior_value="Acme",
                      reviewer_id="jdoe", reason_for_change="full legal name")
    write_certification(store, run_id="r1", source_sha256=SHA, reviewer_id="jdoe",
                        signature_meaning="ok")
    d = per_field_edit_distance(store.read_all())[0]
    assert d.edited is True
    assert d.original_value == "Acme" and d.certified_value == "Acme Corp"
    assert d.distance == pytest.approx(normalized_edit_distance("Acme", "Acme Corp"))


def test_edit_made_after_certification_does_not_count(tmp_path):
    store = _store(tmp_path)
    _extraction(store, "metadata", "sponsorName", "Acme")
    write_certification(store, run_id="r1", source_sha256=SHA, reviewer_id="jdoe",
                        signature_meaning="ok")
    write_review_edit(store, run_id="review", source_sha256=SHA, domain="metadata",
                      field="sponsorName", value="Later Edit", prior_value="Acme",
                      reviewer_id="jdoe", reason_for_change="post-cert tweak")
    d = per_field_edit_distance(store.read_all())[0]
    # the field WAS edited (history contains a REVIEW_EDIT record)...
    assert d.edited is True
    # ...but not as of the certification timestamp, which is what's measured.
    assert d.certified_value == "Acme"


# --- summarize_distances --------------------------------------------------------- #
def test_summarize_distances():
    dists = [FieldEditDistance("metadata", "a", "x", "x", 0.0, False),
            FieldEditDistance("metadata", "b", "y", "yy", 0.5, True)]
    s = summarize_distances(dists)
    assert (s.n_fields, s.n_edited) == (2, 1)
    assert s.mean_distance == 0.25 and s.mean_distance_of_edited == 0.5


def test_summarize_empty_is_none_not_a_crash():
    s = summarize_distances([])
    assert s.n_fields == 0 and s.mean_distance is None and s.mean_distance_of_edited is None


# --- export_edits ------------------------------------------------------------------ #
def test_export_writes_only_edited_fields(tmp_path):
    store = _store(tmp_path)
    _extraction(store, "metadata", "sponsorName", "Acme")            # untouched
    _extraction(store, "metadata", "studyPhase", "Phase 1")
    write_review_edit(store, run_id="review", source_sha256=SHA, domain="metadata",
                      field="studyPhase", value="Phase 2", prior_value="Phase 1",
                      reviewer_id="jdoe", reason_for_change="misread digit")
    write_certification(store, run_id="r1", source_sha256=SHA, reviewer_id="jdoe",
                        signature_meaning="ok")
    out_dir = tmp_path / "edits"
    path = export_edits(SHA, store.read_all(), study_id="StudyX", out_dir=out_dir)
    assert path == out_dir / "StudyX.jsonl"
    labels = read_labels(path)
    assert [(l.domain, l.field, l.value) for l in labels] == [("metadata", "studyPhase", "Phase 2")]
    assert labels[0].labeler == f"review_edit:{SHA[:12]}"


def test_export_returns_none_when_nothing_edited(tmp_path):
    store = _store(tmp_path)
    _extraction(store, "metadata", "sponsorName", "Acme", Decision.AUTO_ACCEPT)
    write_certification(store, run_id="r1", source_sha256=SHA, reviewer_id="jdoe",
                        signature_meaning="ok")
    assert export_edits(SHA, store.read_all(), out_dir=tmp_path / "edits") is None


def test_export_returns_none_when_not_certified(tmp_path):
    store = _store(tmp_path)
    _extraction(store, "metadata", "sponsorName", "Acme")
    write_review_edit(store, run_id="review", source_sha256=SHA, domain="metadata",
                      field="sponsorName", value="Acme Corp", prior_value="Acme",
                      reviewer_id="jdoe", reason_for_change="x")
    assert export_edits(SHA, store.read_all(), out_dir=tmp_path / "edits") is None


def test_export_is_regenerable_not_frozen(tmp_path):
    out_dir = tmp_path / "edits"
    store = _store(tmp_path)
    _extraction(store, "metadata", "sponsorName", "Acme")
    write_review_edit(store, run_id="review", source_sha256=SHA, domain="metadata",
                      field="sponsorName", value="Acme Corp", prior_value="Acme",
                      reviewer_id="jdoe", reason_for_change="x")
    write_certification(store, run_id="r1", source_sha256=SHA, reviewer_id="jdoe",
                        signature_meaning="ok")
    p1 = export_edits(SHA, store.read_all(), study_id="StudyX", out_dir=out_dir)
    # A second certification (re-export) must not raise FileExistsError like
    # the frozen data/labels/fields/ writer would.
    p2 = export_edits(SHA, store.read_all(), study_id="StudyX", out_dir=out_dir)
    assert p1 == p2


def test_certification_time_helper():
    assert certification_time([]) is None
