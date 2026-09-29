"""The conversion API: behaviour of the HTTP layer with a fake converter, plus one
end-to-end conversion through the real core on the synthetic protocol."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from usdm4_api.app import create_app
from usdm4_api.converter import ConversionError, ConversionResult, CoreConverter

PDF = b"%PDF-1.4\n%fake\n"


class FakeConverter:
    name = "fake"

    def __init__(self, fail: bool = False):
        self.fail, self.calls = fail, 0

    def convert(self, pdf_path: Path, work_dir: Path) -> ConversionResult:
        self.calls += 1
        assert pdf_path.read_bytes().startswith(b"%PDF-")
        if self.fail:
            raise ConversionError("could not assemble", {"assembler_errors": ["boom"]})
        return ConversionResult({"study": {"name": "S"}}, {"findings": 3})


def _post(client, data=PDF, name="p.pdf", **kw):
    return client.post("/v1/convert", files={"file": (name, data, "application/pdf")}, **kw)


def test_convert_returns_the_usdm_document():
    r = _post(TestClient(create_app(FakeConverter())))
    assert r.status_code == 200 and r.json() == {"study": {"name": "S"}}
    assert r.headers["X-Converter"] == "fake"


def test_include_report_wraps_the_document():
    r = _post(TestClient(create_app(FakeConverter())), params={"include_report": "true"})
    assert r.json() == {"usdm": {"study": {"name": "S"}}, "report": {"findings": 3}}


def test_a_non_pdf_and_an_empty_upload_are_rejected_before_conversion():
    conv = FakeConverter()
    client = TestClient(create_app(conv))
    assert _post(client, data=b"hello").status_code == 400
    assert _post(client, data=b"").status_code == 400
    assert conv.calls == 0


def test_oversized_uploads_are_refused(monkeypatch):
    monkeypatch.setenv("USDM4_MAX_UPLOAD_MB", "1")
    r = _post(TestClient(create_app(FakeConverter())), data=PDF + b"x" * (2 * 1024 * 1024))
    assert r.status_code == 413


def test_a_conversion_failure_is_a_422_with_the_details():
    r = _post(TestClient(create_app(FakeConverter(fail=True))))
    assert r.status_code == 422
    assert r.json()["assembler_errors"] == ["boom"]


def test_api_keys_are_enforced_when_configured(monkeypatch):
    monkeypatch.setenv("USDM4_API_KEYS", "k1, k2")
    client = TestClient(create_app(FakeConverter()))
    assert _post(client).status_code == 401
    assert _post(client, headers={"X-API-Key": "nope"}).status_code == 401
    assert _post(client, headers={"X-API-Key": "k2"}).status_code == 200
    assert client.get("/health").status_code == 200          # health stays open for probes


def test_health_and_version():
    client = TestClient(create_app(FakeConverter()))
    assert client.get("/health").json() == {"status": "ok", "converter": "fake"}
    assert client.get("/v1/version").json()["converter"] == "fake"


def test_the_real_core_converts_the_synthetic_protocol_end_to_end():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes"))
    from make_full_fixture import build

    pdf = build()
    client = TestClient(create_app(CoreConverter()))
    r = client.post("/v1/convert", params={"include_report": "true"},
                    files={"file": ("protocol.pdf", pdf.read_bytes(), "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    version = body["usdm"]["study"]["versions"][0]
    assert version["studyDesigns"][0]["arms"]
    assert body["report"]["validation"]["structural"]["passed"] is True
    assert body["report"]["run_id"]
