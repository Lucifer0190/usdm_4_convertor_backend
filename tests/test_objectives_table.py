"""Objectives / endpoints / estimands table reader (accuracy fix).

A real Pfizer protocol lays these out as one three-column table whose rows are
tier labels ("Primary:") followed by content rows, repeated header on every
page, and continuation rows when a cell runs onto the next page. Reading rows
keeps each objective, its endpoints and its estimand together — the link that
text matching lost.
"""
from __future__ import annotations

import pymupdf

from usdm4_assure.extract.objectives_table import read_objectives_table

B = "· "


def _pdf(path, page1, page2):
    """A ruled three-column table per page, drawn with PyMuPDF (built-in Helvetica has
    a bullet glyph; the real protocols use a Symbol-font bullet the reader also accepts)."""
    doc = pymupdf.open()
    for rows in (page1, page2):
        page = doc.new_page()
        y = 60.0
        for row in rows:
            height = 44.0
            for i, text in enumerate(row):
                rect = pymupdf.Rect(60 + i * 160, y, 220 + i * 160, y + height)
                page.draw_rect(rect, color=(0, 0, 0), width=0.8)
                page.insert_textbox(rect + (2, 2, -2, -2), text, fontname="helv", fontsize=8)
            y += height
    doc.save(str(path))
    return path


HEADER = ["Objectives", "Endpoints", "Estimands"]
PAGE1 = [HEADER,
         ["Primary:", "Primary:", "Primary:"],
         [B + "To compare efficacy of drug A to placebo.",
          B + "Proportion of participants hospitalised through Day 28.",
          B + "Difference in proportions, treatment policy."],
         ["Key Secondary (Alpha protected):"] * 3,
         [B + "To compare symptom severity.",
          B + "Time to symptom resolution.",
          B + "Difference in median time."]]
PAGE2 = [HEADER,
         ["", "", "for participants who were not receiving background care."],   # estimand continues
         ["Secondary:", "Secondary:", "Secondary:"],
         [B + "To describe the safety of drug A.",
          B + "Incidence of TEAEs. " + B + "Incidence of SAEs.",
          B + "Not applicable."],
         ["Tertiary/Exploratory:"] * 3,
         [B + "To determine PK of drug A.", B + "Drug A PK in plasma.", B + "Not applicable."]]


def test_rows_keep_objective_endpoints_and_estimand_together(tmp_path):
    rows = read_objectives_table(_pdf(tmp_path / "o.pdf", PAGE1, PAGE2), pages=[1, 2])
    assert [r.level for r in rows] == ["Primary", "Secondary", "Secondary", "Exploratory"]
    assert [r.tier for r in rows] == ["Primary", "Key Secondary (Alpha protected)",
                                      "Secondary", "Tertiary/Exploratory"]
    primary = rows[0]
    assert primary.objective == "To compare efficacy of drug A to placebo."
    assert primary.endpoints == ["Proportion of participants hospitalised through Day 28."]


def test_a_continuation_row_extends_the_previous_estimand(tmp_path):
    rows = read_objectives_table(_pdf(tmp_path / "o.pdf", PAGE1, PAGE2), pages=[1, 2])
    key_secondary = rows[1]
    assert key_secondary.estimand.endswith("who were not receiving background care.")
    assert key_secondary.estimand.startswith("Difference in median time.")


def test_several_endpoint_bullets_and_not_applicable_estimand(tmp_path):
    rows = read_objectives_table(_pdf(tmp_path / "o.pdf", PAGE1, PAGE2), pages=[1, 2])
    safety = rows[2]
    assert safety.endpoints == ["Incidence of TEAEs.", "Incidence of SAEs."]
    assert safety.estimand is None                    # "Not applicable." is no estimand


def test_repeated_header_rows_are_not_objectives(tmp_path):
    rows = read_objectives_table(_pdf(tmp_path / "o.pdf", PAGE1, PAGE2), pages=[1, 2])
    assert all(r.objective != "Objectives" for r in rows)
    assert len(rows) == 4


def test_no_table_on_the_pages_returns_an_empty_list(tmp_path):
    empty = _pdf(tmp_path / "e.pdf", [["Just", "text", "here"]], [["more", "more", "more"]])
    assert read_objectives_table(empty, pages=[1, 2]) == []
