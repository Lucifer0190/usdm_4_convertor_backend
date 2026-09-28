"""HTMX review UI (task 5.1) — over the Part 11 audit store, nothing else.

List sources -> field table sorted by risk -> click-to-source crop -> edit ->
certify. Every write is a new, non-destructive :class:`AuditRecord` (see
:mod:`usdm4_assure.audit.writer`); nothing here ever mutates a prior row.

**Localhost only, no auth** (DESIGN.md L9, PLAN.md CP5-A): a human-in-the-loop
tool for a single operator on their own machine, not a multi-tenant service.
Run with::

    uvicorn usdm4_assure.review.app:app --reload
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from usdm4_assure.audit.store import read_source_pointer
from usdm4_assure.audit.writer import write_certification, write_review_edit
from usdm4_assure.review import data as review_data
from usdm4_assure.review.crops import render_crop
from usdm4_assure.review.telemetry import export_edits, per_field_edit_distance, summarize_distances

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = REPO_ROOT / "templates"

app = FastAPI(title="USDM4-Assure review")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _require_records(source_sha256: str) -> list:
    store = review_data.open_store(source_sha256)
    records = store.read_all()
    store.close()
    if not records:
        raise HTTPException(404, f"no audit records for source {source_sha256}")
    return records


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    sources = review_data.list_sources()
    return templates.TemplateResponse(request, "index.html", {"sources": sources})


@app.get("/source/{source_sha256}", response_class=HTMLResponse)
def source_view(request: Request, source_sha256: str) -> HTMLResponse:
    records = _require_records(source_sha256)
    current = review_data.current_fields(records)
    rows = review_data.risk_sorted(list(current.values()))
    summary = review_data.summarize_source(source_sha256, records)
    return templates.TemplateResponse(request, "source.html", {
        "source_sha256": source_sha256, "rows": rows, "summary": summary})


@app.get("/source/{source_sha256}/history/{domain}/{field}", response_class=HTMLResponse)
def field_history(request: Request, source_sha256: str, domain: str, field: str) -> HTMLResponse:
    store = review_data.open_store(source_sha256)
    history = store.read_field(domain, field)
    store.close()
    if not history:
        raise HTTPException(404, f"no records for {domain}.{field}")
    return templates.TemplateResponse(request, "_history.html", {
        "history": history, "source_sha256": source_sha256, "domain": domain, "field": field})


@app.get("/source/{source_sha256}/crop")
def crop(source_sha256: str, page: int, x0: float, y0: float, x1: float, y1: float) -> Response:
    ptr = read_source_pointer(source_sha256)
    if ptr is None:
        raise HTTPException(404, "no source PDF is recorded for this sha256")
    try:
        png = render_crop(ptr["pdf_path"], page, (x0, y0, x1, y1))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(content=png, media_type="image/png")


@app.post("/source/{source_sha256}/fields/{domain}/{field}/edit", response_class=HTMLResponse)
def edit_field(request: Request, source_sha256: str, domain: str, field: str,
              value: str = Form(...), reason: str = Form(...),
              reviewer_id: str = Form(...)) -> HTMLResponse:
    records = _require_records(source_sha256)
    prior = review_data.current_fields(records).get((domain, field))
    store = review_data.open_store(source_sha256)
    rec = write_review_edit(store, run_id="review", source_sha256=source_sha256, domain=domain,
                            field=field, value=value, prior_value=(prior.value if prior else None),
                            reviewer_id=reviewer_id, reason_for_change=reason)
    store.close()
    return templates.TemplateResponse(request, "_row.html", {
        "row": rec, "source_sha256": source_sha256})


@app.post("/source/{source_sha256}/certify", response_class=HTMLResponse)
def certify(request: Request, source_sha256: str, reviewer_id: str = Form(...),
           signature_meaning: str = Form("Reviewed and approved for submission")
           ) -> HTMLResponse:
    _require_records(source_sha256)   # 404 rather than certifying a source with no run
    store = review_data.open_store(source_sha256)
    rec = write_certification(store, run_id="review", source_sha256=source_sha256,
                              reviewer_id=reviewer_id, signature_meaning=signature_meaning)
    records = store.read_all()
    store.close()

    # Post-edit telemetry (task 5.2): now that this run is certified, measure
    # how far its final fields moved from the pipeline's own values, and export
    # any edited field's certified value as a new (non-frozen) label.
    ptr = read_source_pointer(source_sha256)
    study_id = Path(ptr["pdf_path"]).stem if ptr else None
    summary = summarize_distances(per_field_edit_distance(records))
    export_edits(source_sha256, records, study_id=study_id)

    return templates.TemplateResponse(request, "_certified.html", {"row": rec, "summary": summary})
