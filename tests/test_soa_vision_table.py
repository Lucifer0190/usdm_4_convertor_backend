"""The whole-table vision reader: JSON validation and page stitching. No live model: a fake
vision member returns canned JSON."""
from __future__ import annotations

import json

import pymupdf

from usdm4_assure.eval.rubric import score_grid
from usdm4_assure.extract.soa.vision_table import PageReading, _parse, read_soa_vision, stitch


def _page(columns, rows):
    return json.dumps({"is_schedule": True, "columns": columns, "rows": rows})


def test_parse_accepts_fenced_json_and_drops_out_of_range_marks():
    raw = "```json\n" + _page([{"visit": "Day 1"}], [{"activity": "Consent", "marks": [0, 5, "x"]}]) + "\n```"
    r = _parse(raw, 3)
    assert r.page == 3 and r.rows[0]["marks"] == [0]


def test_parse_rejects_non_schedule_and_garbage():
    assert _parse('{"is_schedule": false, "columns": [], "rows": []}', 1) is None
    assert _parse("I cannot read this page", 1) is None


def test_stitch_joins_continuation_pages_and_keeps_same_named_columns_apart():
    cols = [{"visit": "Screening", "epoch": "Screening"}, {"visit": "Day 1", "epoch": "Cycle 1"},
            {"visit": "Day 1", "epoch": ""}]
    p1 = PageReading(1, cols, [{"activity": "Consent", "group": False, "marks": [0]},
                               {"activity": "Labs", "group": False, "marks": [1, 2]}])
    p2 = PageReading(2, cols, [{"activity": "ECG", "group": False, "marks": [2]}])
    g = stitch([p1, p2])
    assert g.visits == ["Screening", "Day 1", "Day 1"]          # two Day 1 columns stay two
    assert g.epochs == ["Screening Period", "Cycle 1", "Cycle 1"]   # band carried right, normalised
    assert (g.activities.index("ECG"), 2) in g.cells


class _FakeVision:
    available = True

    def __init__(self, answers):
        self.answers, self.calls = list(answers), 0

    def complete_vision(self, image_b64, prompt, max_tokens=512):
        self.calls += 1
        assert image_b64 and "Text layer" in prompt
        return self.answers.pop(0)


def test_read_soa_vision_end_to_end_with_a_fake_model(tmp_path):
    doc = pymupdf.open()
    for _ in range(2):
        doc.new_page().insert_text((50, 50), "Consent Day 1 Screening")
    path = tmp_path / "p.pdf"
    doc.save(str(path))
    cols = [{"visit": "Screening"}, {"visit": "Day 1"}]
    llm = _FakeVision([_page(cols, [{"activity": "Consent", "marks": [0]}]), "not json"])
    grid, report = read_soa_vision(path, [1, 2], llm)
    assert grid.visits == ["Screening", "Day 1"] and grid.cells == {(0, 0)}
    assert report.failed == [2] and report.grounded_share == 1.0


def test_no_vision_capability_means_no_grid(tmp_path):
    class _Text:
        available = True
    assert read_soa_vision(tmp_path / "x.pdf", [1], _Text())[0] is None


def test_score_grid_uses_the_soa_categories_only():
    from usdm4_assure.extract.soa.grid import SoAGrid
    ref = {"study": {"versions": [{"studyDesigns": [{
        "epochs": [{"id": "E1", "name": "Screening"}],
        "encounters": [{"id": "V1", "name": "Day 1"}],
        "activities": [{"id": "A1", "name": "Consent"}]}]}]}}
    g = SoAGrid(method="vision", epochs=["Screening"], visits=["Day 1"], activities=["Consent"])
    s = score_grid(g, ref)
    assert set(s.categories) <= {"epochs", "encounters", "activities", "marks"}
    assert s.matched == 3


def test_a_continuation_page_is_told_the_columns_already_found():
    from usdm4_assure.extract.soa.vision_table import _known_columns
    assert _known_columns([]) == ""
    text = _known_columns([PageReading(1, [{"visit": "Week 8"}, {"visit": "ET"}], [])])
    assert "0. Week 8" in text and "1. ET" in text and "exactly these names" in text


def test_vision_names_take_the_geometry_shape():
    from usdm4_assure.extract.soa.vision_table import _column_name
    assert _column_name({"visit_number": "1a a", "visit": "Telephone Call"}) == "Visit 1a"
    assert _column_name({"visit_number": "", "visit": "EOT a"}) == "EOT"
    g = stitch([PageReading(1, [{"visit": "Day 1", "epoch": "Screen."}], [])])
    assert g is None                                  # no rows at all: nothing to deliver
    g = stitch([PageReading(1, [{"visit": "Day 1", "epoch": "Screen."}],
                            [{"activity": "Consent", "group": False, "marks": [0]}])])
    assert g.epochs == ["Screening Period"]


def test_a_footnote_only_continuation_page_is_read_not_failed():
    r = _parse('{"is_schedule": true, "columns": [{"visit": "Day 1"}], "rows": []}', 7)
    assert r is not None and r.rows == []
