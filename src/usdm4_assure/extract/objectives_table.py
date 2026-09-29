"""Objectives / endpoints / estimands table reader (structure, not semantics).

Pfizer protocols (and any ICH E9(R1)-style template) present these as one
three-column table: a header row that repeats on every page, tier rows whose
three cells all read "Primary:" / "Key Secondary (Alpha protected):" / ...,
then content rows whose cells are bullet lists. A cell that runs onto the next
page comes back as a continuation row.

Reading the table by rows keeps an objective, its endpoints and its estimand
together. The estimand-to-endpoint link used to be a text match against a list
extracted some other way; when that list was wrong, all five estimands were
dropped. The row is the link.

Deterministic: PyMuPDF table detection on the given pages, no model.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

_BULLET = re.compile("[•▪●‣·]")
_TIER = re.compile(r"^(primary|secondary|key secondary|tertiary|exploratory|other)\b", re.I)
_NOT_APPLICABLE = re.compile(r"^\s*(not applicable|n/?a)\.?\s*$", re.I)


@dataclass
class ObjectiveRow:
    """One table row: an objective, its endpoints and its estimand."""
    tier: str                      # the label as printed, colon removed
    level: str                     # Primary | Secondary | Exploratory
    objective: str
    endpoints: list[str] = field(default_factory=list)
    estimand: str | None = None
    page: int = 0


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()


def _level(tier: str) -> str:
    low = tier.lower()
    if low.startswith("primary"):
        return "Primary"
    if "tertiary" in low or "exploratory" in low:
        return "Exploratory"
    return "Secondary"


def _bullets(cell: str | None) -> list[str]:
    parts = [_clean(p) for p in _BULLET.split(cell or "")]
    return [p for p in parts if p]


def _is_header(cells: list[str]) -> bool:
    low = " ".join(cells).lower()
    return "objective" in low and "endpoint" in low


def _is_tier(cells: list[str]) -> bool:
    filled = [c for c in cells if c]
    return (len(filled) >= 2 and len(set(filled)) == 1
            and bool(_TIER.match(filled[0])) and not _BULLET.search(filled[0]))


def read_objectives_table(pdf_path: str | Path,
                          pages: Iterable[int]) -> list[ObjectiveRow]:
    """Every objective row in the objectives/endpoints/estimands table.

    Args:
        pdf_path: The source PDF.
        pages: 1-indexed pages that hold the table (from the objectives slot).

    Returns:
        Rows in reading order; ``[]`` when no three-column table is found (the
        caller then falls back to a text reader and reports it).
    """
    import pymupdf

    rows: list[ObjectiveRow] = []
    tier = ""
    fresh_tier = False              # the next content row starts a new record
    doc = pymupdf.open(str(pdf_path))
    try:
        for pno in sorted(set(pages)):
            if not 1 <= pno <= doc.page_count:
                continue
            for table in doc[pno - 1].find_tables().tables:
                for raw in table.extract():
                    if not raw or len(raw) < 3:
                        continue
                    cells = [_clean(c) for c in raw[:3]]
                    if not any(cells) or _is_header(cells):
                        continue
                    if _is_tier(cells):
                        tier, fresh_tier = cells[0].rstrip(":").strip(), True
                        continue
                    starts_new = fresh_tier or bool(_BULLET.match((raw[0] or "").strip()))
                    if not starts_new and not rows:
                        continue            # a table with no tier and no bullets is not this one
                    fresh_tier = False
                    if starts_new:
                        estimand = _clean(_BULLET.sub(" ", raw[2] or ""))
                        rows.append(ObjectiveRow(
                            tier=tier, level=_level(tier),
                            objective=" ".join(_bullets(raw[0])),
                            endpoints=_bullets(raw[1]),
                            estimand=None if _NOT_APPLICABLE.match(estimand) or not estimand
                            else estimand,
                            page=pno))
                        continue
                    # Continuation of the previous row (a cell that ran onto this page).
                    prev = rows[-1]
                    if cells[0]:
                        prev.objective = f"{prev.objective} {cells[0]}".strip()
                    prev.endpoints += _bullets(raw[1])
                    if cells[2]:
                        extra = _clean(_BULLET.sub(" ", raw[2] or ""))
                        if not _NOT_APPLICABLE.match(extra):
                            prev.estimand = f"{prev.estimand or ''} {extra}".strip()
    finally:
        doc.close()
    return rows
