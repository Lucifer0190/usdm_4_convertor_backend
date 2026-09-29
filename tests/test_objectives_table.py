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


# --- ObjectivesExtract built from rows -------------------------------------------- #
def test_extract_objectives_from_rows_keeps_every_endpoint_and_the_estimand(tmp_path):
    from pathlib import Path

    from usdm4_assure.contracts import Document
    from usdm4_assure.extract.objectives import extract_objectives

    rows = read_objectives_table(_pdf(tmp_path / "o.pdf", PAGE1, PAGE2), pages=[1, 2])
    extract = extract_objectives(Document(Path("x.pdf"), [], ""), rows=rows)
    assert [i.level for i in extract.items] == ["Primary", "Secondary", "Secondary", "Exploratory"]
    safety = extract.items[2]
    assert safety.endpoints == ["Incidence of TEAEs.", "Incidence of SAEs."]
    assert safety.endpoint == "Incidence of TEAEs."          # scalar view = first endpoint
    assert extract.items[1].estimand.startswith("Difference in median time.")
    assert extract.decision == "auto_accept"


def test_assembler_block_lists_every_endpoint_of_a_row():
    from usdm4_assure.assemble.study import _objectives_block
    from usdm4_assure.extract.objectives import ObjectivePair, ObjectivesExtract

    block = _objectives_block(ObjectivesExtract(items=[
        ObjectivePair("Describe safety.", "TEAEs.", "Secondary",
                      endpoints=["TEAEs.", "SAEs."])]))
    assert [e["text"] for e in block["objectives"][0]["endpoints"]] == ["TEAEs.", "SAEs."]
    legacy = _objectives_block(ObjectivesExtract(items=[
        ObjectivePair("Assess efficacy.", "PASI 75.", "Primary")]))
    assert [e["text"] for e in legacy["objectives"][0]["endpoints"]] == ["PASI 75."]


# --- the same logical table drawn with different raw column grids ------------------------ #
def _pdf_grid(path, pages, widths):
    """Like ``_pdf`` but with arbitrary column widths (empty spacer columns, as in real files)."""
    doc = pymupdf.open()
    for rows in pages:
        page = doc.new_page()
        y = 60.0
        for row in rows:
            x = 40.0
            for text, w in zip(row, widths, strict=True):
                rect = pymupdf.Rect(x, y, x + w, y + 40)
                page.draw_rect(rect, color=(0, 0, 0), width=0.8)
                page.insert_textbox(rect + (2, 2, -2, -2), text, fontname="helv", fontsize=7)
                x += w
            y += 40
    doc.save(str(path))
    return path


def test_five_raw_columns_with_spacers_and_a_tier_in_the_middle_column(tmp_path):
    W = [150, 30, 150, 120, 20]
    page1 = [["Study Lead-in", "", "", "", ""],
             ["Objectives", "", "Endpoints", "Estimands", ""],
             ["", "Primary", "", "", ""],
             [B + "To determine the dose.", "", B + "Incidence of neutropenia.", B + "See Section 9.", ""],
             ["", "Secondary", "", "", ""],
             [B + "To evaluate safety.", "", B + "Incidence of AEs. " + B + "Incidence of SAEs.", B + "Not Applicable", ""]]
    page2 = [["Phase 3", "", "", "", ""], ["Objectives", "", "Endpoints", "Estimands", ""],
             ["", "Primary", "", "", ""],
             [B + "To show superiority.", "", B + "Progression-free survival.", B + "See Section 9.2.", ""]]
    rows = read_objectives_table(_pdf_grid(tmp_path / "g.pdf", [page1, page2], W), pages=[1, 2])
    assert [(r.part, r.level) for r in rows] == [("Study Lead-in", "Primary"), ("Study Lead-in", "Secondary"),
                                                  ("Phase 3", "Primary")]
    assert rows[0].objective == "To determine the dose."
    assert rows[0].endpoints == ["Incidence of neutropenia."]
    assert rows[1].endpoints == ["Incidence of AEs.", "Incidence of SAEs."] and rows[1].estimand is None
    assert rows[0].estimand == "See Section 9."


def test_two_column_tables_have_no_estimands(tmp_path):
    W = [220, 220]
    page = [["Objectives", "Endpoints*"], ["Primary:", "Primary:"],
            [B + "To evaluate long-term safety.", B + "Incidence of TEAEs."],
            ["Tertiary (Exploratory):", "Tertiary (Exploratory):"],
            [B + "To evaluate the effect on hair.", B + "Response at Week 12."]]
    rows = read_objectives_table(_pdf_grid(tmp_path / "g.pdf", [page], W), pages=[1])
    assert [r.level for r in rows] == ["Primary", "Exploratory"]
    assert rows[0].endpoints == ["Incidence of TEAEs."] and rows[0].estimand is None


def test_tier_labels_with_objective_words_and_key_secondary(tmp_path):
    W = [220, 220]
    page = [["Objectives", "Endpoints"], ["Primary Objective(s):", "Primary Endpoint(s):"],
            [B + "To compare A with B.", B + "PFS by BICR."],
            ["Key Secondary Objectives", "Key Secondary Endpoints"],
            [B + "To compare OS.", B + "Overall survival."]]
    rows = read_objectives_table(_pdf_grid(tmp_path / "g.pdf", [page], W), pages=[1])
    assert [r.level for r in rows] == ["Primary", "Secondary"]
