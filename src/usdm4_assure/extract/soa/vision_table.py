"""Whole-table vision reader for the Schedule of Activities (PLAN.md task C-2).

The geometry reader (``geometry.py``) needs ruling lines and a template it has seen. This
reader needs neither: each page of the schedule is rendered to an image and a frontier
vision model (the ``vision`` role) returns the page's visit columns and marked cells as
JSON. It is a second, independent source for the same grid, so the two can check each
other; which one is delivered where is decided by measurement (task C-3), not assumed.

"LLM proposes, code disposes": the model only says what it sees. Code parses and validates
the JSON, stitches pages into one grid (continuation pages repeat the header; the same visit
on a later table is recognised by :func:`geometry._visit_key`), and reports how many labels
are grounded, i.e. appear verbatim in the page's own text layer.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from usdm4_assure.extract.soa.geometry import _norm_epoch, _strip_footnote, _visit_key
from usdm4_assure.extract.soa.grid import SoAGrid

_PROMPT_FILE = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "soa_vision_page.md"
_MAX_PAGE_TEXT = 6000
_MAX_TOKENS = 24000           # reasoning models spend part of the budget before answering
_ZOOM = 2.0                    # ~144 dpi: small rotated header text stays legible


@dataclass
class PageReading:
    """What the model returned for one page (already validated)."""
    page: int
    columns: list[dict]
    rows: list[dict]


@dataclass
class VisionReport:
    """How the reading went: pages read, pages the model refused or garbled, grounding."""
    pages: list[int] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)
    labels: int = 0
    grounded: int = 0

    @property
    def grounded_share(self) -> float:
        return self.grounded / self.labels if self.labels else 0.0


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _parse(raw: str, page: int) -> PageReading | None:
    """The page's JSON, or ``None`` when it is not a usable schedule reading."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data.get("is_schedule"):
        return None
    columns = [c for c in data.get("columns") or [] if isinstance(c, dict)]
    n = len(columns)
    rows = []
    for r in data.get("rows") or []:
        if not isinstance(r, dict) or not str(r.get("activity") or "").strip():
            continue
        marks = r.get("marks") or []
        marks = sorted({m for m in marks if isinstance(m, int) and 0 <= m < n})
        rows.append({"activity": str(r["activity"]).strip(), "group": bool(r.get("group")),
                     "marks": marks})
    if not columns:
        return None
    return PageReading(page, columns, rows)      # no rows: a footnote-only continuation page


def _render(doc, page: int) -> tuple[str, str]:
    """``(png as base64, text layer)`` of one 1-indexed page."""
    import pymupdf

    p = doc[page - 1]
    png = p.get_pixmap(matrix=pymupdf.Matrix(_ZOOM, _ZOOM)).tobytes("png")
    return base64.b64encode(png).decode("ascii"), p.get_text()


def _known_columns(readings: list[PageReading]) -> str:
    """Columns found on the table's earlier pages, so a continuation page reuses their names."""
    if not readings:
        return ""
    names = [str(c.get("visit") or "") for c in readings[-1].columns]
    listed = "\n".join(f"{i}. {n}" for i, n in enumerate(names))
    return ("Visit columns already found on the previous page of this table, left to right:\n"
            f"{listed}\nIf this page continues the same table, report exactly these columns with "
            "exactly these names, in this order. If it is a different table, read its own header.")


def read_pages(pdf_path: str | Path, pages: list[int], llm) -> tuple[list[PageReading], VisionReport]:
    """Ask the vision model for each page; keep the readings that validate."""
    import pymupdf

    template = _PROMPT_FILE.read_text(encoding="utf-8")
    report = VisionReport()
    readings: list[PageReading] = []
    doc = pymupdf.open(str(pdf_path))
    try:
        for page in pages:
            if not 1 <= page <= doc.page_count:
                continue
            image, text = _render(doc, page)
            prompt = (template.replace("{known_columns}", _known_columns(readings))
                      .replace("{page_text}", text[:_MAX_PAGE_TEXT]))
            report.pages.append(page)
            try:
                raw = llm.complete_vision(image, prompt, max_tokens=_MAX_TOKENS)
            except Exception:  # noqa: BLE001 - one bad page must not sink the table
                report.failed.append(page)
                continue
            reading = _parse(raw, page)
            if reading is None:
                report.failed.append(page)
                continue
            readings.append(reading)
            page_text = _norm(text)
            labels = [c.get("visit", "") for c in reading.columns] + \
                     [r["activity"] for r in reading.rows]
            report.labels += len(labels)
            report.grounded += sum(1 for s in labels if s and _norm(s) in page_text)
    finally:
        doc.close()
    return readings, report


def _column_name(col: dict) -> str:
    """The visit name in the same shape the geometry reader gives, so the two readers compare:
    a numbered visit is "Visit 1a"; otherwise the printed label without footnote letters."""
    number = _strip_footnote(str(col.get("visit_number") or ""))
    if re.fullmatch(r"\d+[a-z]?", number):
        return f"Visit {number}"
    return _strip_footnote(str(col.get("visit") or ""))


def stitch(readings: list[PageReading]) -> SoAGrid | None:
    """One grid from the page readings, in page order."""
    visits: list[str] = []
    timings: list[str] = []
    epochs: list[str] = []
    visit_at: dict[str, int] = {}
    activities: list[str] = []
    activity_at: dict[str, int] = {}
    cells: set[tuple[int, int]] = set()
    for reading in readings:
        where: list[int] = []
        seen_here: dict[str, int] = {}
        for col in reading.columns:
            name = _column_name(col)
            base = _visit_key(name) or "col"
            seen_here[base] = seen_here.get(base, 0) + 1
            key = f"{base}#{seen_here[base]}"   # two "Day 1" columns on a page stay two visits
            if key not in visit_at:
                visit_at[key] = len(visits)
                visits.append(name or f"V{len(visits) + 1}")
                window = str(col.get("window") or "").strip()
                timings.append(f"{name} {window}".strip())
                epochs.append(_norm_epoch(_strip_footnote(str(col.get("epoch") or ""))))
            where.append(visit_at[key])
        for row in reading.rows:
            key = re.sub(r"\W+", "", row["activity"].lower())
            if key not in activity_at:
                activity_at[key] = len(activities)
                activities.append(row["activity"])
            for m in row["marks"]:
                cells.add((activity_at[key], where[m]))
    if not visits or not activities:
        return None
    # A column with no epoch of its own continues the one before it (merged band).
    for i in range(1, len(epochs)):
        epochs[i] = epochs[i] or epochs[i - 1]
    return SoAGrid(method="vision", epochs=epochs, visits=visits, timings=timings,
                   activities=activities, cells=cells)


def read_soa_vision(pdf_path: str | Path, pages: list[int], llm) -> tuple[SoAGrid | None, VisionReport]:
    """Read the schedule on ``pages`` with the vision model.

    Returns ``(None, report)`` when the model has no vision capability or no page yields a
    schedule; the caller keeps the geometry reading in that case.
    """
    if getattr(llm, "complete_vision", None) is None or not getattr(llm, "available", False):
        return None, VisionReport()
    readings, report = read_pages(pdf_path, pages, llm)
    return stitch(readings), report
