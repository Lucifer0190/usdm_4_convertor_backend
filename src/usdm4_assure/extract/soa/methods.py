"""Independent SoA table extractors — the ensemble members for the SoA grid.

  pdfplumber        : ruling-line based table detection, single-page-only
  pymupdf           : PyMuPDF's own find_tables(), single-page-only
  pymupdf_stitched  : the same, but joined across pages first (task 2.3)
  vision            : frontier VLM cell-content pass (task 2.5)

Two independent deterministic implementations give a real agreement signal for
the cross-validation step without needing an LLM.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from usdm4_assure.extract.soa.grid import SoAGrid
from usdm4_assure.llm.base import LLM

if TYPE_CHECKING:
    from usdm4_assure.soa.stitch import StitchedGrid

_MARK_RE = re.compile(r"[xX✓✔●•]")


def _is_mark(cell: str | None) -> bool:
    return bool(cell and _MARK_RE.search(cell.strip()))


def _parse_rows(rows: list[list[str | None]], method: str) -> SoAGrid:
    """Rows: [epochRow, visitRow, timingRow, *activityRows]; col 0 = row label."""
    g = SoAGrid(method=method)
    rows = [r for r in rows if r and any(c and str(c).strip() for c in r)]
    if len(rows) < 4:
        return g
    epoch_row, visit_row, timing_row, *body = rows

    def clean(cells: list) -> list[str]:
        return [(str(c).strip() if c else "") for c in cells[1:]]

    g.epochs = _ffill(clean(epoch_row))     # forward-fill spanned epoch cells
    g.visits = clean(visit_row)
    g.timings = clean(timing_row)
    ncol = len(g.visits)

    for ai, row in enumerate(body):
        label = (str(row[0]).strip() if row and row[0] else "")
        if not label:
            continue
        foot = bool(re.search(r"\s[a-z]$", label))   # trailing footnote marker
        label = re.sub(r"\s+[a-z]$", "", label).strip()
        g.activities.append(label)
        if foot:
            g.footnote_activities.add(label)
        for vi in range(min(ncol, len(row) - 1)):
            if _is_mark(row[vi + 1]):
                g.cells.add((len(g.activities) - 1, vi))
    return g


def _ffill(vals: list[str]) -> list[str]:
    out, last = [], ""
    for v in vals:
        last = v or last
        out.append(last)
    return out


def extract_pdfplumber(pdf_path: str | Path, pages: list[int] | None = None) -> SoAGrid:
    """First table with visits and activities. ``pages`` (1-indexed) restricts the
    search to the schedule-of-activities pages the section graph located."""
    import pdfplumber
    with pdfplumber.open(str(pdf_path)) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            if pages is not None and number not in pages:
                continue
            tables = page.extract_tables()
            for t in tables:
                g = _parse_rows(t, "pdfplumber")
                if g.visits and g.activities:
                    return g
    return SoAGrid(method="pdfplumber")


def extract_pymupdf(pdf_path: str | Path, pages: list[int] | None = None) -> SoAGrid:
    """First table with visits and activities, optionally only on ``pages`` (1-indexed)."""
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    try:
        for number, page in enumerate(doc, start=1):
            if pages is not None and number not in pages:
                continue
            finder = page.find_tables()
            for t in finder.tables:
                g = _parse_rows(t.extract(), "pymupdf")
                if g.visits and g.activities:
                    return g
    finally:
        doc.close()
    return SoAGrid(method="pymupdf")


def extract_pymupdf_stitched(pdf_path: str | Path,
                             pages: list[int] | None = None) -> SoAGrid | None:
    """Multi-page-aware pymupdf extraction: layout adapter -> stitcher -> SoAGrid.

    Without ``pages``, every table in the document is a candidate — with no
    section routing yet (Phase 3), the table with the most activities after
    conversion wins, which is noisy on a long protocol with several 3-row-
    header tables. Callers that already know the SoA's page range (e.g. from
    a hand-labelled ground truth, or a future section graph) should pass it.

    Returns ``None`` (never a partial/guessed grid) when no table was found,
    the stitcher couldn't confidently join a multi-page table, or the
    resulting table's header isn't the 3-row (epoch/visit/timing) shape this
    project's ``SoAGrid``/``TimelineAssembler`` mapping models — see
    ``soa.from_stitched``. Callers fall back to :func:`extract_pymupdf`
    (single-page-only) in that case.
    """
    from usdm4_assure.layout.pymupdf_adapter import extract_tables
    from usdm4_assure.soa.from_stitched import stitched_to_soa_grid
    from usdm4_assure.soa.stitch import stitch

    tables = extract_tables(pdf_path, pages)
    if not tables:
        return None
    candidates = [sg for g in stitch(tables).grids
                 if (sg := stitched_to_soa_grid(g)) is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda sg: len(sg.activities))


def extract_vision(pdf_path: str | Path, grid: StitchedGrid, vision: LLM,
                   vision_alt: LLM | None = None) -> SoAGrid | None:
    """VLM cell-content pass (task 2.5): an independent third ensemble member.

    Every activity-row data cell of ``grid`` is cropped from the source PDF
    and read with the ``vision`` role model, escalating to a different-family
    ``vision_alt`` only where that reading disagrees with the grid's own
    parsed text (``soa.vision_cells``). Returns ``None`` when ``vision`` has
    no vision capability or key, so the deterministic members carry the run —
    the same pattern as the text-LLM ensemble member.
    """
    from usdm4_assure.soa.from_stitched import is_mark, normalize_header, stitched_to_soa_grid
    from usdm4_assure.soa.vision_cells import read_grid

    if not getattr(vision, "available", False) or getattr(vision, "complete_vision", None) is None:
        return None
    base = stitched_to_soa_grid(grid)
    if base is None:
        return None

    g = SoAGrid(method="vision", epochs=base.epochs, visits=base.visits,
               timings=base.timings, activities=base.activities,
               footnote_activities=base.footnote_activities)
    grid = normalize_header(grid)
    col_to_vi = {j: vi for vi, j in enumerate(grid.data_columns())}
    for r in read_grid(pdf_path, grid, vision, vision_alt):
        text = r.vision_alt_text or r.vision_text or ""
        if is_mark(text) and r.col in col_to_vi:
            g.cells.add((r.row, col_to_vi[r.col]))
    return g
