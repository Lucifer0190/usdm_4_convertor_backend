"""Header layouts beyond the basic template: numbered visits, cycle bands, footnote letters,
and a continuation page that lost one column rule. Synthetic PDFs, no protocol data."""
from __future__ import annotations

import pymupdf
import pytest

from usdm4_assure.extract.soa.geometry import (
    _CYCLE,
    _is_prose,
    _name_from_roles,
    _strip_footnote,
    _visit_key,
    read_soa_geometry,
)

LINE = 0.7


def _table(page, top, xs, rows, skip_x=()):
    """Rows of single cells; every rule drawn except vertical rules at ``skip_x``."""
    h = 16
    for r, cells in enumerate(rows):
        y = top + r * h
        page.draw_rect(pymupdf.Rect(xs[0], y - LINE / 2, xs[-1], y + LINE / 2), color=None, fill=(0, 0, 0))
        for x in xs:
            if x not in skip_x:
                page.draw_rect(pymupdf.Rect(x - LINE / 2, y, x + LINE / 2, y + h), color=None,
                               fill=(0, 0, 0))
        for c, text in enumerate(cells):
            if text:
                page.insert_text((xs[c] + 3, y + 11), text, fontsize=6, fontname="helv")
    y = top + len(rows) * h
    page.draw_rect(pymupdf.Rect(xs[0], y - LINE / 2, xs[-1], y + LINE / 2), color=None, fill=(0, 0, 0))


def _pdf(tmp_path, pages):
    doc = pymupdf.open()
    for draw in pages:
        draw(doc.new_page(width=792, height=612))
    path = tmp_path / "soa.pdf"
    doc.save(str(path))
    return path


# --- helpers --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("raw", "clean"), [
    ("EOT / Withdrawal a", "EOT / Withdrawal"), ("Day 1 b, c", "Day 1"), ("±2d*", "±2d"),
    ("Visit 2a", "Visit 2a"), ("Cycles 1 and 2", "Cycles 1 and 2"), ("Part A", "Part A")])
def test_footnote_letters_are_stripped_but_real_words_kept(raw, clean):
    assert _strip_footnote(raw) == clean


@pytest.mark.parametrize("text", ["Cycle 1", "Cycles 1 and 2", "Cycles ≥3", "C2"])
def test_cycle_band_headers_are_recognised(text):
    assert _CYCLE.match(text)


def test_a_numbered_visit_is_named_by_its_number_and_windows_stay_out_of_the_name():
    name, window, desc = _name_from_roles(
        [("id", "1a a"), ("", "Telephone Call"), ("window", "21-35 Days After Visit 1")])
    assert (name, window, desc) == ("Visit 1a", "21-35 Days After Visit 1", "Telephone Call")


def test_an_unnumbered_visit_is_named_by_its_description():
    assert _name_from_roles([("id", "Unplanned"), ("", "Suspected Acute Visit")])[0] == \
        "Suspected Acute Visit"


# --- whole tables ------------------------------------------------------------------------ #
def test_a_visit_number_row_names_visits_and_is_not_an_epoch_band(tmp_path):
    xs = [40, 160, 250, 340, 430]
    rows = [["Visit Number", "1", "1a a", "2"],
            ["Visit Identifier b", "Dose 1", "Telephone Call", "Dose 2"],
            ["Visit Window", "Jul 2022 to Mar 2023", "N/A", "50-70 Days After Visit 1"],
            ["Informed consent", "X", "", ""],
            ["Blood draw", "X", "", "X"]]
    g = read_soa_geometry(_pdf(tmp_path, [lambda p: _table(p, 80, xs, rows)]))
    assert g.visits == ["Visit 1", "Visit 1a", "Visit 2"]
    assert not any(e in ("1", "1a", "2") for e in g.epochs)
    assert "Jul 2022" not in " ".join(g.visits)
    assert (1, 2) in g.cells and (0, 0) in g.cells


def test_a_continuation_page_missing_a_column_rule_is_still_one_table(tmp_path):
    xs = [40, 160, 230, 300, 370, 440]
    header = [["Protocol Activity", "Screening", "Day 1", "Day 15", "EOT a"],
              ["Visit Window", "", "±2", "±2", ""]]
    p1 = header + [["Consent", "X", "", "", ""], ["Labs", "X", "X", "X", "X"]]
    p2 = header + [["ECG", "", "X", "", ""], ["AE review", "", "", "X", ""]]
    path = _pdf(tmp_path, [lambda p: _table(p, 80, xs, p1),
                           lambda p: _table(p, 80, xs, p2, skip_x={370})])
    g = read_soa_geometry(path)
    assert g.visits == ["Screening", "Day 1", "Day 15", "EOT"]          # not appended twice
    ecg = g.activities.index("ECG")
    assert {v for a, v in g.cells if a == ecg} == {1}                   # mapped by position
    ae = g.activities.index("AE review")
    assert 2 in {v for a, v in g.cells if a == ae}


@pytest.mark.parametrize(("a", "b"), [
    ("Cycle 1 Day 1", "Cycle 1 Day 1 0 h (within 2.5 h prior to dose ** )"),
    ("Cycle 2 Day 1", "Cycle 2 Day 1 5-7"), ("EOT / Withdrawal", "EoT/Withdra wal")])
def test_a_pk_table_column_is_the_same_visit_as_the_main_schedule(a, b):
    assert _visit_key(a) == _visit_key(b)


@pytest.mark.parametrize(("a", "b"), [("Weeks 1-4", "Weeks 5-8"), ("Day 1", "Day 15"),
                                      ("Day -1", "Day 1")])
def test_different_visits_keep_different_keys(a, b):
    assert _visit_key(a) != _visit_key(b)


def test_a_sentence_across_the_table_is_prose_not_a_header():
    assert _is_prose("The purpose of the prescreening visit is to obtain blood samples to "
                     "evaluate the participant's status. Screening activities may be performed.")
    assert not _is_prose("Active Treatment Phase (1 Cycle = 28 days)")


def test_a_later_table_repeating_main_visits_adds_marks_not_visits(tmp_path):
    xs = [40, 160, 230, 300, 370]
    main = [["Protocol Activity", "Screening", "Cycle 1 Day 1", "Cycle 2 Day 1"],
            ["Consent", "X", "", ""], ["Labs", "X", "X", "X"]]
    pk = [["PK Activity", "Cycle 1 Day 1 0 h", "Cycle 1 Day 1 2 h", "Cycle 2 Day 1 0 h", "Notes"],
          ["PK sample", "X", "X", "X", ""]]
    path = _pdf(tmp_path, [lambda p: _table(p, 80, xs, main),
                           lambda p: _table(p, 80, [40, 160, 230, 300, 370, 520], pk)])
    g = read_soa_geometry(path)
    assert g.visits == ["Screening", "Cycle 1 Day 1", "Cycle 2 Day 1"]
    pk_row = g.activities.index("PK sample")
    assert {v for a, v in g.cells if a == pk_row} == {1, 2}


def test_a_comments_column_is_not_a_visit(tmp_path):
    xs = [40, 160, 230, 300, 470]
    rows = [["General Activities", "Prescreening", "Day 1", "Comments"],
            ["Consent", "X", "", "Must be signed first"], ["Demography", "X", "X", ""]]
    g = read_soa_geometry(_pdf(tmp_path, [lambda p: _table(p, 80, xs, rows)]))
    assert g.visits == ["Prescreening", "Day 1"]
