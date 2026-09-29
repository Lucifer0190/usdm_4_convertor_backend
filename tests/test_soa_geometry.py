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


@pytest.mark.parametrize("text,is_mark", [
    ("X", True), ("x", True), ("X (a)", True), ("X\u1d48", True), ("\u2713", True), ("\u25cf", True),
    ("X (to be performed every cycle)", True), ("X, see Note 2", True),
    ("as per standard of care", False), ("See Section 8.3", False), ("", False), ("0 days", False),
    ("Xenon", False), ("(\u00b1 1 day)", False),
])
def test_what_counts_as_a_mark(text, is_mark):
    from usdm4_assure.extract.soa.geometry import _MARK
    assert bool(_MARK.match(text)) is is_mark


# --- layout families seen across the packet (label-free, so they generalise) ---------- #
def _oncology_pdf(tmp_path):
    """Caption above the table; a merged Cycle band; a Study Week numeric row; a merged
    window cell; a narrow column that wraps 'Screening'; a merged cell 'as per standard of care'."""
    xs = [50, 170, 200, 230, 260, 290, 330, 560]           # label | Screen | C1 | C1 | C2 | C2 | EOT | notes
    doc = pymupdf.open()
    page = doc.new_page(width=792, height=612)
    top = 100
    _text(page, 50, top - 6, "Table 1. Study Schedule of Activities", size=8)
    rows_y = [top, top + 16, top + 30, top + 60, top + 76]      # header bands then body rows
    band_edges = {0: [0, 1, 2, 4, 6, 7],                       # Screen | Cycle 1 (2 cols) | Cycle 2 (2 cols) | EOT+notes
                  1: list(range(8)), 2: [0, 1, 2, 6, 7],           # window cell merged over both cycles
                  3: list(range(8))}
    for r in range(4):
        y0, y1 = rows_y[r], rows_y[r + 1]
        for i in band_edges[r]:
            _vline(page, xs[i], y0, y1)
    for y in rows_y:
        _hline(page, y, xs[0], xs[-1])
    _text(page, xs[0] + 3, top + 11, "Visit Identifier")
    _text(page, xs[1] + 3, top + 11, "Screen", size=6)
    _text(page, xs[1] + 3, top + 18, "ing", size=6)              # wrapped mid-word in a narrow cell
    _text(page, xs[2] + 8, top + 11, "Cycle 1")
    _text(page, xs[4] + 8, top + 11, "Cycle 2")
    _text(page, xs[6] + 3, top + 11, "EOT")
    _text(page, xs[0] + 3, top + 26, "Study Week")
    for i, w in enumerate(["1", "2", "5", "6"]):
        _text(page, xs[2 + i] + 8, top + 26, w)
    _text(page, xs[0] + 3, top + 45, "Visit Window")
    _text(page, xs[2] + 8, top + 45, "(+/- 3 days)", size=6)
    y = rows_y[4]
    _hline(page, y, xs[0], xs[-1])
    for label, marks in (("Consent", [0]), ("Vitals", [0, 1, 2, 3, 4, 5]), ("Scans", [])):
        for x in xs:
            _vline(page, x, y, y + 16)
        _text(page, xs[0] + 3, y + 11, label)
        for m in marks:
            _text(page, xs[1 + m] + 10, y + 11, "X")
        y += 16
        _hline(page, y, xs[0], xs[-1])
    # merged row: one cell spanning the four cycle columns
    for x in (xs[0], xs[1], xs[6], xs[7]):
        _vline(page, x, y, y + 16)
    _text(page, xs[0] + 3, y + 11, "Physical exam")
    _text(page, xs[2] + 20, y + 11, "as per standard of care")
    _hline(page, y + 16, xs[0], xs[-1])
    path = tmp_path / "onc.pdf"
    doc.save(str(path))
    return path


def test_a_caption_above_the_table_is_not_a_header_band(tmp_path):
    g = read_soa_geometry(_oncology_pdf(tmp_path), pages=[1])
    assert g is not None
    assert not any("Table 1" in e for e in g.epochs)


def test_a_word_wrapped_inside_a_narrow_cell_is_rejoined(tmp_path):
    g = read_soa_geometry(_oncology_pdf(tmp_path), pages=[1])
    assert g.visits[0].startswith("Screening")


def test_cycle_bands_prefix_the_visits_under_them_and_keep_names_unique(tmp_path):
    g = read_soa_geometry(_oncology_pdf(tmp_path), pages=[1])
    assert g.visits[1] == "Cycle 1 Week 1" and g.visits[2] == "Cycle 1 Week 2"
    assert g.visits[3] == "Cycle 2 Week 5"
    assert len(set(g.visits)) == len(g.visits)


def test_a_merged_window_cell_applies_to_every_visit_it_spans(tmp_path):
    g = read_soa_geometry(_oncology_pdf(tmp_path), pages=[1])
    assert all("+/- 3 days" in t for t in g.timings[1:5])
    assert "+/-" not in g.visits[1]


def test_a_merged_note_cell_marks_every_visit_it_spans(tmp_path):
    g = read_soa_geometry(_oncology_pdf(tmp_path), pages=[1])
    a = {n: i for i, n in enumerate(g.activities)}
    assert {(a["Physical exam"], v) for v in (1, 2, 3, 4)} <= g.cells


def test_the_page_header_underline_is_not_part_of_the_table(tmp_path):
    """A rule under the running header lies above the table; the heading text between the
    two must not become a header band (it did: the section intro read as an epoch)."""
    src = _oncology_pdf(tmp_path)
    doc = pymupdf.open(str(src))
    page = doc[0]
    _hline(page, 70, 50, 742)                                        # running-header underline
    _text(page, 50, 90, "1.3. Schedule of Activities  The SoA table provides an overview")
    out = tmp_path / "with_header_rule.pdf"
    doc.save(str(out))
    g = read_soa_geometry(out, pages=[1])
    assert g is not None
    assert not any("provides an overview" in e for e in g.epochs)
