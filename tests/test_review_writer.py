"""Reviewer-facing audit records (task 5.1): edits, certification, source pointers."""
from __future__ import annotations

from usdm4_assure.audit.store import AuditStore, read_source_pointer, record_source
from usdm4_assure.audit.writer import write_certification, write_review_edit
from usdm4_assure.contracts import Decision, Method
from usdm4_assure.contracts_audit import AuditEvent


def _store(tmp_path) -> AuditStore:
    return AuditStore(path=tmp_path / "run.sqlite")


# --- source pointer --------------------------------------------------------------- #
def test_record_source_then_read(tmp_path):
    record_source("ab" * 32, "/data/protocol.pdf", base_dir=tmp_path)
    ptr = read_source_pointer("ab" * 32, base_dir=tmp_path)
    assert ptr["pdf_path"] == "/data/protocol.pdf" and "recorded_at" in ptr


def test_read_missing_source_pointer_is_none(tmp_path):
    assert read_source_pointer("nope", base_dir=tmp_path) is None


def test_record_source_first_write_wins(tmp_path):
    record_source("ab" * 32, "/first.pdf", base_dir=tmp_path)
    record_source("ab" * 32, "/second.pdf", base_dir=tmp_path)
    assert read_source_pointer("ab" * 32, base_dir=tmp_path)["pdf_path"] == "/first.pdf"


# --- review edit -------------------------------------------------------------------- #
def test_review_edit_is_human_auto_accept_with_full_confidence(tmp_path):
    store = _store(tmp_path)
    rec = write_review_edit(store, run_id="review-1", source_sha256="ab" * 32,
                            domain="metadata", field="sponsorName", value="Acme Corp",
                            prior_value="Acme", reviewer_id="jdoe",
                            reason_for_change="Sponsor legal name corrected on title page")
    assert rec.event is AuditEvent.REVIEW_EDIT
    assert rec.method is Method.HUMAN and rec.decision is Decision.AUTO_ACCEPT
    assert rec.confidence == 1.0
    assert rec.prior_value == "Acme" and rec.value == "Acme Corp"
    assert rec.reviewer_id == "jdoe"
    assert store.read_all() == [rec]


def test_review_edit_history_is_append_only(tmp_path):
    store = _store(tmp_path)
    write_review_edit(store, run_id="r1", source_sha256="ab" * 32, domain="metadata",
                      field="sponsorName", value="Acme", prior_value=None,
                      reviewer_id="jdoe", reason_for_change="initial")
    write_review_edit(store, run_id="r2", source_sha256="ab" * 32, domain="metadata",
                      field="sponsorName", value="Acme Corp", prior_value="Acme",
                      reviewer_id="jdoe", reason_for_change="correction")
    history = store.read_field("metadata", "sponsorName")
    assert [r.value for r in history] == ["Acme", "Acme Corp"]
    assert history[1].prior_value == "Acme"


# --- certification -------------------------------------------------------------------- #
def test_certification_record(tmp_path):
    store = _store(tmp_path)
    rec = write_certification(store, run_id="run1", source_sha256="ab" * 32,
                              reviewer_id="jdoe",
                              signature_meaning="Reviewed and approved for submission")
    assert rec.event is AuditEvent.CERTIFY and rec.reviewer_id == "jdoe"
    assert rec.signature_meaning == "Reviewed and approved for submission"
    assert rec.field is None
