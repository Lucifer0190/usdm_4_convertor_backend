"""Geometry-first Schedule of Activities reader.

Word-generated protocol PDFs draw their tables as thin ruling rectangles; those
rules give the exact visit columns and rows (merged header cells simply have
fewer rules), and rotated header labels keep their text direction. The reader
therefore needs no table-structure model: rules -> grid, lines -> cells, glyphs
-> marks. Synthetic PDFs here mimic the real layout: a merged period band, rotated
visit labels with a window line, a merged group row, an "X" matrix, a notes column,
and a continuation page that repeats the header.
"""
from __future__ import annotations

import pymupdf
import pytest

from usdm4_assure.extract.soa.geometry import read_soa_geometry

# label | Screen | Baseline | Day 5 | Day 10 | ET | notes
XS = [50, 170, 210, 250, 290, 330, 370, 560]
LINE = 0.7


def _vline(page, x, y0, y1):
    page.draw_rect(pymupdf.Rect(x - LINE / 2, y0, x + LINE / 2, y1), color=None, fill=(0, 0, 0))


def _hline(page, y, x0, x1):
    page.draw_rect(pymupdf.Rect(x0, y - LINE / 2, x1, y + LINE / 2), color=None, fill=(0, 0, 0))


def _text(page, x, y, s, size=7):
    page.insert_text((x, y), s, fontsize=size, fontname="helv")


def _rotated(page, x, top, bottom, s):
    """Text reading bottom-to-top, like the real visit labels."""
    page.insert_text((x + 7, bottom - 3), s, fontsize=6.5, fontname="helv", rotate=90)


def _header(page, top):
    """Band 1: periods (Treatment merges Baseline+Day 5, F/U merges Day 10+ET);
    band 2: rotated visit labels and the day window line."""
    band1, band2 = top + 24, top + 24 + 70
    for x in XS:
        _vline(page, x, top, band1) if x not in (250, 330) else None   # merged spans: no rule
        _vline(page, x, band1, band2)
    _text(page, XS[0] + 3, top + 14, "Visit Identifier")
    _text(page, XS[1] + 3, top + 14, "Screen.")
    _text(page, XS[2] + 12, top + 14, "Treatment Period")
    _text(page, XS[4] + 12, top + 14, "F/U")
    _text(page, XS[6] + 60, top + 14, "Notes")
    for y in (top, band1, band2):
        _hline(page, y, XS[0], XS[-1])
    _rotated(page, XS[2] + 1, band1, band2, "Baseline")
    _rotated(page, XS[2] + 12, band1, band2, "(Day 1)")
    _rotated(page, XS[3] + 3, band1, band2, "Day 5")
    _rotated(page, XS[4] + 3, band1, band2, "Day 10")
    _rotated(page, XS[5] + 3, band1, band2, "(prior to Day 34)")
    _text(page, XS[1] + 3, band2 - 8, "Day -1 to Day 1", size=5)
    _text(page, XS[3] + 14, band2 - 30, "(+/-1 day)", size=4)
    return band2


def _body(page, y, rows):
    for label, marks in rows:
        h = 14
        _hline(page, y, XS[0], XS[-1])
        if marks is None:                            # group row: merged, no inner rules
            _vline(page, XS[0], y, y + h)
            _vline(page, XS[-1], y, y + h)
        else:
            for x in XS:
                _vline(page, x, y, y + h)
            for col in marks:
                _text(page, XS[1 + col] + 10, y + 10, "X")
        _text(page, XS[0] + 3, y + 10, label)
        y += h
    _hline(page, y, XS[0], XS[-1])
    return y


@pytest.fixture()
def soa_pdf(tmp_path):
    doc = pymupdf.open()
    p1 = doc.new_page(width=792, height=612)
    y = _header(p1, 100)
    _body(p1, y, [("ELIGIBILITY", None), ("Informed consent", [0]), ("Vital signs", [0, 1, 2]),
                  ("PK sample", [2])])
    p2 = doc.new_page(width=792, height=612)                      # continuation: header repeats
    y = _header(p2, 60)
    _body(p2, y, [("Study intervention", [1]), ("Vital status check", [3])])
    path = tmp_path / "soa.pdf"
    doc.save(str(path))
    return path


def test_visit_columns_come_from_the_ruling_lines(soa_pdf):
    g = read_soa_geometry(soa_pdf, pages=[1, 2])
    assert g is not None and g.method == "geometry"
    assert len(g.visits) == 5
    assert g.visits[1].startswith("Baseline (Day 1)")
    assert g.visits[2].startswith("Day 5") and g.visits[3].startswith("Day 10")
    assert g.visits[4].startswith("(prior to Day 34)")


def test_screening_column_takes_its_day_window_label(soa_pdf):
    g = read_soa_geometry(soa_pdf, pages=[1, 2])
    assert g.visits[0].startswith("Day -1 to Day 1")


def test_merged_period_cells_become_epochs_for_every_column_they_span(soa_pdf):
    g = read_soa_geometry(soa_pdf, pages=[1, 2])
    assert g.epochs == ["Screening Period", "Treatment Period", "Treatment Period",
                        "Follow-up Period", "Follow-up Period"]


def test_activities_include_group_rows_and_continuation_rows_without_repeating_the_header(soa_pdf):
    g = read_soa_geometry(soa_pdf, pages=[1, 2])
    assert g.activities == ["ELIGIBILITY", "Informed consent", "Vital signs", "PK sample",
                            "Study intervention", "Vital status check"]


def test_marks_are_assigned_by_glyph_position(soa_pdf):
    g = read_soa_geometry(soa_pdf, pages=[1, 2])
    a = {name: i for i, name in enumerate(g.activities)}
    assert (a["Informed consent"], 0) in g.cells
    assert {(a["Vital signs"], v) for v in (0, 1, 2)} <= g.cells
    assert (a["PK sample"], 2) in g.cells
    assert (a["Study intervention"], 1) in g.cells
    assert (a["Vital status check"], 3) in g.cells
    assert len(g.cells) == 1 + 3 + 1 + 1 + 1


def test_the_window_line_is_kept_apart_from_the_visit_name(soa_pdf):
    g = read_soa_geometry(soa_pdf, pages=[1, 2])
    assert "(+/-1 day)" not in g.visits[2]
    assert "+/-1" in g.timings[2]


def test_no_ruled_table_returns_none(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "no table here")
    path = tmp_path / "plain.pdf"
    doc.save(str(path))
    assert read_soa_geometry(path, pages=[1]) is None
