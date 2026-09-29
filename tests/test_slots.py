"""Section slots and furniture stripping (accuracy fix: narrow, clean evidence).

Covers only our code, on synthetic documents: a slot is found by title meaning
(never by section number), spans end at the next section of the same or higher
level, nested matches are not double counted, and repeating page furniture is
removed without touching a table header that merely repeats a few times.
"""
from __future__ import annotations

from pathlib import Path

from usdm4_assure.contracts import Block, Document
from usdm4_assure.sections.graph import Section, SectionGraph
from usdm4_assure.sections.slots import (
    SLOTS,
    slot_document,
    slot_pages,
    strip_furniture,
)


def _doc(*blocks: tuple[int, float, str]) -> Document:
    bl = [Block(text=t, page=p, bbox=(72.0, y, 500.0, y + 12)) for p, y, t in blocks]
    return Document(source=Path("x.pdf"), blocks=bl, full_text="\n".join(b.text for b in bl))


def _graph(*secs: tuple[str, int, int, float]) -> SectionGraph:
    """``(title, level, page, y)`` -> a graph in reading order."""
    return SectionGraph([Section(title=t, number="", level=lv, page=p, y=y, source="bookmark")
                         for t, lv, p, y in secs], "bookmark")


PROTOCOL = (
    ("1.1. Synopsis", 2, 2, 100.0),
    ("1.3. Schedule of Activities", 2, 3, 100.0),
    ("Table 1. Study Schedule of Activities - Screening", 3, 3, 110.0),
    ("Table 2. Study Schedule of Activities - Follow-up", 3, 4, 100.0),
    ("3. OBJECTIVES, ENDPOINTS, AND ESTIMANDS", 1, 5, 100.0),
    ("4. STUDY DESIGN", 1, 6, 100.0),
    ("5.1. Inclusion Criteria", 2, 7, 100.0),
    ("5.2. Exclusion Criteria", 2, 7, 400.0),
    ("5.3. Lifestyle Considerations", 2, 8, 100.0),
)
DOC = _doc(
    (1, 50.0, "Title page Protocol C1"),
    (2, 110.0, "synopsis text"),
    (3, 120.0, "soa table 1 text"), (4, 120.0, "soa table 2 text"),
    (5, 120.0, "objectives table text"),
    (6, 120.0, "overall design text"),
    (7, 120.0, "1. Age 18 or older."), (7, 420.0, "1. Pregnancy."),
    (8, 120.0, "lifestyle text"),
)


def test_slot_is_found_by_title_meaning_not_number():
    win = slot_document(DOC, _graph(*PROTOCOL), "inclusion")
    assert win is not None
    assert [b.text for b in win.document.blocks] == ["1. Age 18 or older."]


def test_a_span_ends_at_the_next_section_of_the_same_or_higher_level():
    exc = slot_document(DOC, _graph(*PROTOCOL), "exclusion")
    assert [b.text for b in exc.document.blocks] == ["1. Pregnancy."]


def test_nested_matches_are_not_double_counted_and_pages_are_reported():
    graph = _graph(*PROTOCOL)
    win = slot_document(DOC, graph, "soa")
    assert [b.text for b in win.document.blocks] == ["soa table 1 text", "soa table 2 text"]
    assert win.pages == [3, 4]                  # content pages only
    assert slot_pages(graph, "soa") == [3, 4, 5]   # graph-only bound: the next section starts mid-page 5


def test_a_missing_slot_returns_none_instead_of_the_whole_document():
    assert slot_document(DOC, _graph(("Introduction", 1, 1, 10.0)), "inclusion") is None


def test_numbering_variants_and_alternate_titles_still_resolve():
    graph = _graph(("2 Schedule of Assessments", 1, 3, 100.0), ("4 Objectives", 1, 5, 100.0),
                   ("6.1 Inclusion Criteria", 2, 7, 100.0), ("7 Something", 1, 9, 1.0))
    for slot in ("soa", "objectives", "inclusion"):
        assert slot_document(DOC, graph, slot) is not None, slot
    assert set(SLOTS) >= {"synopsis", "soa", "objectives", "inclusion", "exclusion",
                          "design", "interventions"}


def test_front_matter_is_added_on_request():
    win = slot_document(DOC, _graph(*PROTOCOL), "synopsis", front_pages=1)
    assert [b.text for b in win.document.blocks] == ["Title page Protocol C1", "synopsis text"]


# --- furniture ---------------------------------------------------------------------- #
WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
         "india", "juliet", "kilo", "lima"]


def _long_doc(n_pages=12):
    blocks = []
    for p in range(1, n_pages + 1):
        blocks.append((p, 20.0, f"PFIZER CONFIDENTIAL CT02-GSOP Template Phase 1 2 3 4 Page {p}"))
        blocks.append((p, 300.0, f"real body text {WORDS[p - 1]} discussion"))
    for p in (3, 4, 5):  # a table header repeated on three pages only
        blocks.append((p, 200.0, "Objectives Endpoints Estimands"))
    return _doc(*blocks)


def test_repeating_page_furniture_is_removed_even_when_a_page_number_changes():
    out = strip_furniture(_long_doc())
    texts = [b.text for b in out.blocks]
    assert not any("PFIZER CONFIDENTIAL" in t for t in texts)
    assert sum("real body text" in t for t in texts) == 12
    assert "PFIZER CONFIDENTIAL" not in out.full_text


def test_a_table_header_repeated_on_a_few_pages_is_kept():
    out = strip_furniture(_long_doc())
    assert sum(b.text == "Objectives Endpoints Estimands" for b in out.blocks) == 3


def test_strip_furniture_keeps_character_geometry_for_grounding():
    doc = _long_doc()
    doc.chars = {1: []}
    assert strip_furniture(doc).chars is doc.chars


def test_long_furniture_is_removed_even_where_its_height_differs():
    blocks = []
    for p in range(1, 13):
        blocks.append((p, 20.0 if p != 7 else 540.0,      # landscape page: footer sits lower
                       f"PFIZER CONFIDENTIAL CT02-GSOP Template Page {p}"))
        blocks.append((p, 300.0, f"body {WORDS[p - 1]} text"))
    out = strip_furniture(_doc(*blocks))
    assert not any("PFIZER CONFIDENTIAL" in b.text for b in out.blocks)
