"""Structural invariants — quality checks that need no reference labels.

Labels exist for eight studies. There are 204 real Pfizer protocols. Invariants are the
way to measure generalisation on all of them: each is a property that must hold for
*any* correctly read protocol (a schedule's visit columns each hold at least one mark,
eligibility numbering runs 1..N, an objectives row has an endpoint). A failure is
therefore evidence of a layout family the readers do not handle, independent of any one
study's reference, and fixing it is a general fix rather than a fit to one document.

The functions are pure (they take what a reader returned), so they are cheap to test;
:func:`check_protocol` runs them over one PDF end to end.
"""
from __future__ import annotations

import re
from pathlib import Path

from usdm4_assure.extract.soa.grid import SoAGrid

_PLACEHOLDER_VISIT = re.compile(r"^V\d+$")


def soa_invariants(grid: SoAGrid | None, pages: list[int] | None) -> dict[str, bool]:
    """Invariants of a read Schedule of Activities. ``True`` = holds."""
    inv: dict[str, bool] = {"slot_found": bool(pages), "grid_found": grid is not None}
    if grid is None:
        inv["enough_visits_and_activities"] = False
        return inv
    n_v, n_a = len(grid.visits), len(grid.activities)
    inv["enough_visits_and_activities"] = n_v >= 2 and n_a >= 5
    inv["marks_are_in_range"] = all(0 <= a < n_a and 0 <= v < n_v for a, v in grid.cells)
    marked_visits = {v for _, v in grid.cells}
    inv["every_visit_has_a_mark"] = n_v > 0 and len(marked_visits) == n_v
    marked_rows = {a for a, _ in grid.cells}
    inv["most_activities_are_scheduled"] = n_a > 0 and len(marked_rows) / n_a >= 0.6
    inv["visit_names_are_real"] = all(v.strip() and not _PLACEHOLDER_VISIT.match(v.strip())
                                      for v in grid.visits)
    inv["every_visit_has_an_epoch"] = all(e.strip() for e in grid.epochs) and len(grid.epochs) == n_v
    inv["activity_names_are_label_sized"] = all(0 < len(a) <= 300 for a in grid.activities)
    inv["visit_names_are_unique_enough"] = n_v == 0 or len(set(grid.visits)) / n_v >= 0.8
    return inv


def eligibility_invariants(inclusion: list[str], exclusion: list[str]) -> dict[str, bool]:
    items = inclusion + exclusion
    return {
        "has_inclusion": bool(inclusion),
        "has_exclusion": bool(exclusion),
        # A criterion can be two words ("Trisomy 21") or several paragraphs with sub-items.
        "items_are_criterion_sized": bool(items) and all(4 <= len(i) <= 3500 for i in items),
        "list_sizes_are_plausible": 1 <= len(inclusion) <= 60 and 1 <= len(exclusion) <= 80,
    }


def objectives_invariants(rows: list) -> dict[str, bool]:
    return {
        "table_found": bool(rows),
        "has_a_primary_objective": any(r.level == "Primary" for r in rows),
        "every_row_has_an_endpoint": bool(rows) and all(r.endpoints for r in rows),
        "objective_text_is_real": bool(rows) and all(len(r.objective) >= 15 for r in rows),
    }


def check_protocol(pdf_path: str | Path) -> dict:
    """Read one protocol with the section, table and list readers and check invariants."""
    from usdm4_assure.extract.eligibility import split_numbered
    from usdm4_assure.extract.objectives_table import read_objectives_table
    from usdm4_assure.extract.soa.geometry import read_first_schedule
    from usdm4_assure.ingest.pdf import ingest
    from usdm4_assure.sections.graph import build_graph
    from usdm4_assure.sections.slots import SLOTS, slot_document, slot_windows, strip_furniture

    pdf_path = Path(pdf_path)
    doc = strip_furniture(ingest(pdf_path))
    graph = build_graph(doc, pdf_path)
    windows = {name: slot_document(doc, graph, name) for name in SLOTS}
    out: dict = {"file": pdf_path.name, "pages": len({b.page for b in doc.blocks}),
                 "outline": graph.source,
                 "slots": {name: w is not None for name, w in windows.items()}}

    groups = [w.pages for w in slot_windows(doc, graph, "soa")]
    grid, used = read_first_schedule(pdf_path, groups)
    out["soa"] = soa_invariants(grid, groups[max(used, 0)] if groups else None)
    out["soa_stats"] = grid.stats() if grid else None
    out["soa_pages"] = groups[max(used, 0)] if groups else None
    out["soa_groups"] = len(groups)

    inc, exc = windows["inclusion"], windows["exclusion"]
    inc_items = split_numbered(inc.document.full_text) if inc else []
    exc_items = split_numbered(exc.document.full_text) if exc else []
    out["eligibility"] = eligibility_invariants(inc_items, exc_items)
    out["eligibility_counts"] = [len(inc_items), len(exc_items)]

    obj = windows["objectives"]
    rows = read_objectives_table(pdf_path, obj.pages) if obj else []
    out["objectives"] = objectives_invariants(rows)
    out["objectives_rows"] = len(rows)
    return out
