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

    def __init__(self, fail: bool = False, llm: bool = True):
        self.fail, self.calls, self._llm = fail, 0, llm

    def llm_ready(self) -> bool:
        return self._llm

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
    assert client.get("/health").json() == {"status": "ok", "converter": "fake", "llm": True}
    assert client.get("/v1/version").json()["converter"] == "fake"


def test_the_llm_pipeline_is_required_by_default():
    conv = FakeConverter(llm=False)
    client = TestClient(create_app(conv))
    r = _post(client)
    assert r.status_code == 503 and "OPEN_ROUTER_KEY" in r.json()["detail"]
    assert conv.calls == 0
    assert client.get("/health").json()["llm"] is False


def test_deterministic_only_must_be_allowed_explicitly(monkeypatch):
    monkeypatch.setenv("USDM4_ALLOW_NO_LLM", "1")
    assert _post(TestClient(create_app(FakeConverter(llm=False)))).status_code == 200


def test_the_real_core_converts_the_synthetic_protocol_end_to_end(monkeypatch):
    monkeypatch.setenv("USDM4_ALLOW_NO_LLM", "1")      # the test suite runs without an LLM key
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


def test_a_scanned_pdf_with_no_text_layer_is_refused_cleanly_not_a_500(monkeypatch, tmp_path):
    monkeypatch.setenv("USDM4_ALLOW_NO_LLM", "1")
    import pymupdf
    doc = pymupdf.open()
    for _ in range(10):
        page = doc.new_page(width=612, height=792)
        page.draw_rect(pymupdf.Rect(50, 50, 550, 750), color=(0, 0, 0))
    scan_path = tmp_path / "scan.pdf"
    doc.save(str(scan_path))
    doc.close()

    client = TestClient(create_app(CoreConverter()))
    r = client.post("/v1/convert", files={"file": ("scan.pdf", scan_path.read_bytes(),
                                                    "application/pdf")})
    assert r.status_code == 422
    assert r.json()["reason"] == "scanned_pdf_no_ocr"


# --- async jobs, headers, input checks ---------------------------------------------------- #
def _wait_done(client, jid, tries=50):
    import time
    for _ in range(tries):
        body = client.get(f"/v1/jobs/{jid}").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_a_job_is_accepted_at_once_and_polled_to_its_result():
    with TestClient(create_app(FakeConverter())) as client:
        r = client.post("/v1/jobs", files={"file": ("p.pdf", PDF, "application/pdf")})
        assert r.status_code == 202 and r.json()["status"] == "queued"
        body = _wait_done(client, r.json()["id"])
        assert body["status"] == "done" and body["result"] == {"study": {"name": "S"}}


def test_a_failed_job_reports_the_same_error_a_direct_call_would():
    with TestClient(create_app(FakeConverter(fail=True))) as client:
        jid = client.post("/v1/jobs", files={"file": ("p.pdf", PDF, "application/pdf")}).json()["id"]
        body = _wait_done(client, jid)
        assert body["status"] == "failed" and body["http_status"] == 422
        assert body["error"]["assembler_errors"] == ["boom"]


def test_jobs_are_validated_up_front_and_unknown_ids_are_404():
    client = TestClient(create_app(FakeConverter()))
    assert client.post("/v1/jobs", files={"file": ("p.pdf", b"hello", "application/pdf")}).status_code == 400
    assert client.get("/v1/jobs/nope").status_code == 404


def test_jobs_need_the_api_key_and_the_llm(monkeypatch):
    monkeypatch.setenv("USDM4_API_KEYS", "k1")
    client = TestClient(create_app(FakeConverter()))
    assert client.post("/v1/jobs", files={"file": ("p.pdf", PDF, "application/pdf")}).status_code == 401
    assert client.get("/v1/jobs/x").status_code == 401
    monkeypatch.delenv("USDM4_API_KEYS")
    down = TestClient(create_app(FakeConverter(llm=False)))
    assert down.post("/v1/jobs", files={"file": ("p.pdf", PDF, "application/pdf")}).status_code == 503


def test_the_run_id_is_a_response_header():
    class WithRun(FakeConverter):
        def convert(self, pdf_path, work_dir):
            return ConversionResult({"study": {}}, {"run_id": "run-42", "findings": 1})

    r = _post(TestClient(create_app(WithRun())))
    assert r.headers["X-Run-Id"] == "run-42"


def _pdf_file(tmp_path, name, build):
    import pymupdf
    doc = pymupdf.open()
    build(doc)
    path = tmp_path / name
    build_kw = {}
    if name.startswith("enc"):
        build_kw = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "owner_pw": "o", "user_pw": "u"}
    doc.save(str(path), **build_kw)
    doc.close()
    return path.read_bytes()


def test_a_corrupt_pdf_and_an_encrypted_pdf_are_refused_with_a_reason(monkeypatch, tmp_path):
    monkeypatch.setenv("USDM4_ALLOW_NO_LLM", "1")
    client = TestClient(create_app(CoreConverter()))
    corrupt = b"%PDF-1.4\n1 0 obj << /Broken >>\nnot a real pdf at all\n"
    r = _post(client, data=corrupt)
    assert r.status_code == 422 and r.json()["reason"] == "corrupt_pdf"
    encrypted = _pdf_file(tmp_path, "enc.pdf", lambda d: d.new_page().insert_text((72, 72), "Secret"))
    r = _post(client, data=encrypted)
    assert r.status_code == 422 and r.json()["reason"] == "encrypted_pdf"


def test_core_is_requested_only_when_the_flag_is_set(monkeypatch):
    conv = CoreConverter()
    monkeypatch.delenv("USDM4_RUN_CORE", raising=False)
    assert conv.core_enabled() is False
    monkeypatch.setenv("USDM4_RUN_CORE", "1")
    assert conv.core_enabled() is True
