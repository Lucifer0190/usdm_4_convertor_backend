"""Objectives / endpoints / estimands table reader (structure, not semantics).

Pfizer protocols (and any ICH E9(R1)-style template) present these as one logical table:
a header row (Objectives | Endpoints | Estimands, repeated on every page), tier rows
("Primary:", "Key Secondary", "Tertiary/Exploratory"), optional part or phase title rows
("Part 1", "Study Lead-in", "Phase 3"), then content rows whose cells are bullet lists. A cell
that runs onto the next page comes back as a continuation row.

The *raw* grid differs from file to file: two columns, three, five with empty spacer columns,
nine with merged spans. The tier label may repeat in every cell or sit alone in the middle
one. So the reader first maps raw columns to the three logical ones from the header row
(each header owns the columns up to the next header), then reads rows.

Reading by rows keeps an objective, its endpoints and its estimand together. The
estimand-to-endpoint link used to be a text match against a list extracted some other way;
when that list was wrong, every estimand was dropped. The row is the link.

Deterministic: PyMuPDF table detection on the given pages, no model.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

_BULLET = re.compile("[•▪●‣·]")
_TIER = re.compile(r"^(primary|secondary|key secondary|tertiary|exploratory|other|"
                   r"safety|efficacy)\b", re.IGNORECASE)
_NOT_APPLICABLE = re.compile(r"^\s*(not applicable|n/?a)\.?\s*$", re.IGNORECASE)
_HEADER_CELL = re.compile(r"^(objectives?|endpoints?|estimands?)[\s*:]*$", re.IGNORECASE)
_TIER_TAIL = re.compile(r"\s*(objectives?|endpoints?)?\s*(\(s\))?\s*:?\s*$", re.IGNORECASE)


@dataclass
class ObjectiveRow:
    """One table row: an objective, its endpoints and its estimand."""
    tier: str                      # the label as printed, colon removed
    level: str                     # Primary | Secondary | Exploratory
    objective: str
    endpoints: list[str] = field(default_factory=list)
    estimand: str | None = None
    page: int = 0
    part: str = ""                 # "Part 1", "Study Lead-in", "Phase 3" when the table has parts


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


def _header_spans(cells: list[str]) -> dict[str, tuple[int, int]] | None:
    """Raw column span of each logical column, from a header row; ``None`` if not a header."""
    marks: dict[str, int] = {}
    for i, c in enumerate(cells):
        m = _HEADER_CELL.match(c)             # exactly "Objectives", "Endpoints*", "Estimands"
        if m and m.group(1).lower().rstrip("s") not in marks:
            marks[m.group(1).lower().rstrip("s")] = i
    if "objective" not in marks or "endpoint" not in marks:
        return None
    order = sorted(marks.items(), key=lambda kv: kv[1])
    spans = {}
    for n, (key, start) in enumerate(order):
        end = order[n + 1][1] - 1 if n + 1 < len(order) else len(cells) - 1
        spans[key] = (start, end)
    return spans


def _logical(cells: list[str], spans: dict[str, tuple[int, int]]) -> dict[str, str]:
    """The logical cells of a raw row (empty spacer columns dropped)."""
    return {key: " ".join(c for c in cells[a:b + 1] if c.strip()) for key, (a, b) in spans.items()}


def _tier_or_part(raw: list[str],
                  spans: dict[str, tuple[int, int]] | None = None) -> tuple[str, str] | None:
    """``("tier", label)`` / ``("part", label)`` when the row is a label row, else ``None``.

    A label row has the same text in several cells, or text in one cell that lies in the
    objectives columns (a lone cell in the endpoint or estimand columns is the continuation
    of a cell that ran onto the next page, not a label). No bullets.
    """
    filled = [c for c in raw if c]
    if not filled or _BULLET.search(" ".join(filled)):
        return None
    if len(filled) == 1 and spans is not None and raw.index(filled[0]) > spans["objective"][1]:
        return None
    texts = {re.sub(r"\(s\)|objectives?|endpoints?", "", t, flags=re.IGNORECASE).strip(" :*") for t in filled}
    if len(texts) != 1:
        return None
    text = filled[0]
    collapsed = re.sub(r"\s+", "", text)
    if not _TIER.match(text) and len(text.split()) == 2 and _TIER.match(collapsed):
        text = collapsed                       # "Second ary": a narrow cell wrapped the word
    if _TIER.match(text):
        label = _TIER_TAIL.sub("", text).rstrip(":").strip()
        return "tier", label or text.rstrip(":")
    if len(text) <= 40 and not text.rstrip().endswith("."):
        return "part", text.rstrip(":")
    return None


def read_objectives_table(pdf_path: str | Path,
                          pages: Iterable[int]) -> list[ObjectiveRow]:
    """Every objective row in the objectives/endpoints/estimands table.

    Args:
        pdf_path: The source PDF.
        pages: 1-indexed pages that hold the table (from the objectives slot).

    Returns:
        Rows in reading order; ``[]`` when no table with an Objectives and an Endpoints
        header is found (the caller then falls back to a text reader and reports it).
    """
    import pymupdf

    rows: list[ObjectiveRow] = []
    tier, part = "", ""
    fresh_tier = False              # the next content row starts a new record
    spans: dict[str, tuple[int, int]] | None = None
    doc = pymupdf.open(str(pdf_path))
    try:
        for pno in sorted(set(pages)):
            if not 1 <= pno <= doc.page_count:
                continue
            for table in doc[pno - 1].find_tables().tables:
                for raw_row in table.extract():
                    cells = [(c or "").replace("\n", " ") for c in (raw_row or [])]
                    raw = [_clean(c) for c in cells]
                    if not any(raw):
                        continue
                    header = _header_spans(raw)
                    if header is not None:
                        spans = header                    # header (also repeated per page)
                        continue
                    label = _tier_or_part(raw, spans)
                    if spans is None:
                        if label and label[0] == "part":  # a title row above the header
                            part = label[1]
                        continue
                    if label is not None:
                        if label[0] == "tier":
                            tier, fresh_tier = label[1], True
                        else:
                            part = label[1]
                        continue
                    if len(cells) <= max(v[1] for v in spans.values()):
                        continue
                    logical = _logical(cells, spans)
                    obj_cell = logical.get("objective", "")
                    starts_new = fresh_tier or bool(_BULLET.match(obj_cell.strip()))
                    if not starts_new and not rows:
                        continue
                    est_text = _clean(_BULLET.sub(" ", logical.get("estimand", "")))
                    if starts_new:
                        fresh_tier = False
                        rows.append(ObjectiveRow(
                            tier=tier, level=_level(tier),
                            objective=" ".join(_bullets(obj_cell)),
                            endpoints=_bullets(logical.get("endpoint", "")),
                            estimand=None if _NOT_APPLICABLE.match(est_text) or not est_text
                            else est_text,
                            page=pno, part=part))
                        continue
                    prev = rows[-1]                       # continuation onto this page
                    if obj_cell.strip():
                        prev.objective = f"{prev.objective} {_clean(obj_cell)}".strip()
                    prev.endpoints += _bullets(logical.get("endpoint", ""))
                    if est_text and not _NOT_APPLICABLE.match(est_text):
                        prev.estimand = f"{prev.estimand or ''} {est_text}".strip()
    finally:
        doc.close()
    return rows
