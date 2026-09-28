"""HTMX review UI (task 5.1): API list, crop endpoint, audited edits.

Each test builds its own audit store + source pointer (the fixture below),
so nothing here depends on a prior pipeline run.
"""
from __future__ import annotations

import pymupdf
import pytest
from fastapi.testclient import TestClient

from usdm4_assure.audit.store import record_source
from usdm4_assure.audit.writer import write_field_decision
from usdm4_assure.contracts import (
    AssuredField,
    Decision,
    GroundedCandidate,
    Method,
    Quote,
    VerifyPass,
)
from usdm4_assure.contracts_audit import AuditEvent
from usdm4_assure.review import data as review_data
from usdm4_assure.review.app import app

SHA = "ab" * 32


@pytest.fixture
def pdf(tmp_path):
    """A one-page PDF with real text, so a crop actually renders."""
    path = tmp_path / "protocol.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Northwind Therapeutics, Inc.", fontsize=14)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def seeded_source(pdf):
    """Writes one AUTO_ACCEPT field with a resolved quote, and returns (client, sha)."""
    record_source(SHA, pdf)
    store = review_data.open_store(SHA)
    quote = Quote("Northwind Therapeutics, Inc.", VerifyPass.EXACT, page=1,
                 char_start=0, char_end=29, bbox=(72.0, 90.0, 250.0, 110.0))
    winner = GroundedCandidate("sponsorName", "Northwind Therapeutics, Inc.",
                               Method.LLM_FRONTIER, quote, model_id="openai/gpt-5.1")
    assured = AssuredField("sponsorName", "Northwind Therapeutics, Inc.", [winner], True, 2,
                           "supported", 0.92, Decision.AUTO_ACCEPT, quote=quote,
                           domain="metadata")
    write_field_decision(store, run_id="run1", source_sha256=SHA, domain="metadata",
                         assured=assured)
    store.close()
    return TestClient(app), SHA


# --- listing -------------------------------------------------------------------- #
def test_index_lists_seeded_source(seeded_source):
    client, sha = seeded_source
    resp = client.get("/")
    assert resp.status_code == 200
    assert sha[:12] in resp.text or "protocol.pdf" in resp.text


def test_index_with_no_sources_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("USDM4_AUDIT_DIR", str(tmp_path / "empty"))
    resp = TestClient(app).get("/")
    assert resp.status_code == 200 and "No runs found" in resp.text


# --- source view ------------------------------------------------------------------ #
def test_source_view_shows_the_field(seeded_source):
    client, sha = seeded_source
    resp = client.get(f"/source/{sha}")
    assert resp.status_code == 200
    assert "sponsorName" in resp.text and "Northwind Therapeutics" in resp.text
    assert "auto_accept" in resp.text


def test_unknown_source_is_404(seeded_source):
    client, _sha = seeded_source
    assert client.get("/source/" + "00" * 32).status_code == 404


# --- crop ------------------------------------------------------------------------- #
def test_crop_returns_a_real_png(seeded_source):
    client, sha = seeded_source
    resp = client.get(f"/source/{sha}/crop", params={"page": 1, "x0": 72.0, "y0": 90.0,
                                                      "x1": 250.0, "y1": 110.0})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_crop_out_of_range_page_is_404(seeded_source):
    client, sha = seeded_source
    resp = client.get(f"/source/{sha}/crop", params={"page": 99, "x0": 0, "y0": 0,
                                                      "x1": 10, "y1": 10})
    assert resp.status_code == 404


def test_crop_unknown_source_is_404(seeded_source):
    client, _sha = seeded_source
    resp = client.get(f"/source/{'00' * 32}/crop", params={"page": 1, "x0": 0, "y0": 0,
                                                            "x1": 10, "y1": 10})
    assert resp.status_code == 404


# --- edit ---------------------------------------------------------------------------- #
def test_edit_appends_a_review_record_and_returns_updated_row(seeded_source):
    client, sha = seeded_source
    resp = client.post(f"/source/{sha}/fields/metadata/sponsorName/edit",
                       data={"value": "Northwind Therapeutics", "reason": "Trimmed suffix",
                             "reviewer_id": "jdoe"})
    assert resp.status_code == 200
    assert "Northwind Therapeutics" in resp.text and "jdoe" not in resp.text  # value in row, not reviewer

    store = review_data.open_store(sha)
    history = store.read_field("metadata", "sponsorName")
    store.close()
    assert [r.event for r in history] == [AuditEvent.EXTRACTION, AuditEvent.REVIEW_EDIT]
    edit = history[-1]
    assert edit.value == "Northwind Therapeutics"
    assert edit.prior_value == "Northwind Therapeutics, Inc."
    assert edit.reviewer_id == "jdoe" and edit.reason_for_change == "Trimmed suffix"
    assert edit.method is Method.HUMAN and edit.decision is Decision.AUTO_ACCEPT


def test_source_view_reflects_the_edit_as_current(seeded_source):
    client, sha = seeded_source
    client.post(f"/source/{sha}/fields/metadata/sponsorName/edit",
               data={"value": "Edited Value", "reason": "test", "reviewer_id": "jdoe"})
    resp = client.get(f"/source/{sha}")
    assert "Edited Value" in resp.text


def test_history_endpoint_lists_every_record(seeded_source):
    client, sha = seeded_source
    client.post(f"/source/{sha}/fields/metadata/sponsorName/edit",
               data={"value": "Edited Value", "reason": "test", "reviewer_id": "jdoe"})
    resp = client.get(f"/source/{sha}/history/metadata/sponsorName")
    assert resp.status_code == 200
    assert "extraction" in resp.text and "review_edit" in resp.text


# --- certify --------------------------------------------------------------------------- #
def test_certify_appends_a_certify_record(seeded_source):
    client, sha = seeded_source
    resp = client.post(f"/source/{sha}/certify",
                       data={"reviewer_id": "jdoe", "signature_meaning": "Approved for use"})
    assert resp.status_code == 200 and "Certified" in resp.text and "jdoe" in resp.text

    store = review_data.open_store(sha)
    records = store.read_all()
    store.close()
    cert = [r for r in records if r.event is AuditEvent.CERTIFY]
    assert len(cert) == 1
    assert cert[0].reviewer_id == "jdoe" and cert[0].signature_meaning == "Approved for use"


def test_certified_source_shows_as_certified_on_index(seeded_source):
    client, sha = seeded_source
    client.post(f"/source/{sha}/certify",
               data={"reviewer_id": "jdoe", "signature_meaning": "Approved"})
    resp = client.get("/")
    assert "certified" in resp.text


def test_certify_unknown_source_is_404(seeded_source):
    client, _sha = seeded_source
    resp = client.post(f"/source/{'00' * 32}/certify",
                       data={"reviewer_id": "jdoe", "signature_meaning": "x"})
    assert resp.status_code == 404
