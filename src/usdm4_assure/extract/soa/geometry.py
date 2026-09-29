"""Geometry-first Schedule of Activities reader.

Word-generated protocol PDFs (every Pfizer protocol measured) draw their tables as
thin ruling rectangles. Those rules are the table: vertical rules give the exact
visit columns, horizontal rules the rows, and a merged header cell is simply a band
with fewer rules. Header labels that are rotated 90 degrees keep their text
direction, so they can be read by position like any other line. No table-structure
model is needed, and none of the failure modes of one (fragmented columns, merged
rows, cross-page splits) apply.

Pipeline, per table:

1. rules -> column edges and row edges (``_grid``);
2. text lines -> cells by centre point, rotated lines ordered by their direction;
3. header rows are those above the first group row or first row holding a mark;
4. a header cell spanning several columns is an *epoch* for all of them, a cell over
   one column contributes to that visit's label; day-window fragments ("(+/-1 day)",
   "0 days") are split off into the timing text;
5. body rows are activities (a merged row with a label is a group heading, kept as a
   row because reference USDMs keep it); marks are short cell texts starting with
   ``X`` or a tick/bullet glyph;
6. later pages continue the table when their column edges match (repeated header
   rows are recognised by their text and skipped); a table with different columns
   (Table 2 of a split SoA) is appended as more visit columns, with activity rows
   unified by name.

The result is the project's existing :class:`SoAGrid`, so the cross-validation and
assembly path is unchanged.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from usdm4_assure.extract.soa.grid import SoAGrid

_TOL = 1.6                    # points: rules closer than this are the same rule
_MIN_COVERAGE = 0.30          # of the table's height/width, for a rule to define a column/row
_MARK = re.compile(r"^\s*[xX\u2713\u2714\u2022\u25cf\u25a0\u221a\u00d7](?:$|[\s(\[,;.\u00b9\u00b2\u00b3\u2070-\u209f\u1d2c-\u1d6a])")
_WINDOW = re.compile(r"^\(?\s*(?:[±+\-−]|\+/-)\s*\d|^\d+\s*days?\)?$|^window", re.IGNORECASE)
_EPOCH_NAMES = (
    (re.compile(r"^screen", re.I), "Screening Period"),
    (re.compile(r"^(treatment|dosing|intervention)", re.I), "Treatment Period"),
    (re.compile(r"^(f/?u|follow)", re.I), "Follow-up Period"),
)
_UNIT_HINT = re.compile(r"(?<![a-z])(day|week|month|cycle)s?(?![a-z])\s*(\([^)]*\))?", re.IGNORECASE)
_EXTENDS_PREVIOUS = re.compile(r"^(et|early term\w*|unscheduled|eot|end of treatment)\b", re.I)


@dataclass(frozen=True)
class _Seg:
    pos: float
    lo: float
    hi: float


@dataclass
class _Line:
    text: str
    bbox: tuple[float, float, float, float]
    rotated: bool
    reads_up: bool

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2


@dataclass
class _Table:
    page: int
    col_edges: list[float]
    row_edges: list[float]
    vertical: list[_Seg]
    lines: list[_Line]
    body_start: int = 0


# --- rules ------------------------------------------------------------------------- #
def _rules(page) -> tuple[list[_Seg], list[_Seg]]:
    """Vertical ``(x, y0, y1)`` and horizontal ``(y, x0, x1)`` rule segments."""
    vs: list[_Seg] = []
    hs: list[_Seg] = []
    for g in page.get_drawings():
        stroked = g.get("color") is not None
        for item in g["items"]:
            kind = item[0]
            if kind == "l":
                a, b = item[1], item[2]
                if abs(a.x - b.x) < 0.8 and abs(a.y - b.y) > 4:
                    vs.append(_Seg(a.x, min(a.y, b.y), max(a.y, b.y)))
                elif abs(a.y - b.y) < 0.8 and abs(a.x - b.x) > 4:
                    hs.append(_Seg(a.y, min(a.x, b.x), max(a.x, b.x)))
            elif kind == "re":
                r = item[1]
                if r.width <= 2.0 and r.height > 4:
                    vs.append(_Seg((r.x0 + r.x1) / 2, r.y0, r.y1))
                elif r.height <= 2.0 and r.width > 4:
                    hs.append(_Seg((r.y0 + r.y1) / 2, r.x0, r.x1))
                elif stroked and r.width > 2.0 and r.height > 2.0:
                    vs += [_Seg(r.x0, r.y0, r.y1), _Seg(r.x1, r.y0, r.y1)]
                    hs += [_Seg(r.y0, r.x0, r.x1), _Seg(r.y1, r.x0, r.x1)]
    return vs, hs


def _cluster(segs: list[_Seg]) -> list[tuple[float, list[tuple[float, float]]]]:
    """Group segments by position (within tolerance); merge overlapping intervals."""
    out: list[tuple[float, list[tuple[float, float]]]] = []
    for s in sorted(segs, key=lambda s: s.pos):
        if out and abs(out[-1][0] - s.pos) <= _TOL:
            pos, ivs = out[-1]
            n = len(ivs)
            out[-1] = ((pos * n + s.pos) / (n + 1), ivs + [(s.lo, s.hi)])
        else:
            out.append((s.pos, [(s.lo, s.hi)]))
    merged = []
    for pos, ivs in out:
        ivs.sort()
        cur = [list(ivs[0])]
        for lo, hi in ivs[1:]:
            if lo <= cur[-1][1] + 2.0:
                cur[-1][1] = max(cur[-1][1], hi)
            else:
                cur.append([lo, hi])
        merged.append((pos, [(a, b) for a, b in cur]))
    return merged


def _coverage(ivs: list[tuple[float, float]]) -> float:
    return sum(b - a for a, b in ivs)


def _table_box(vs: list[_Seg], hs: list[_Seg]) -> tuple[float, float, float, float] | None:
    """Bounding box of the largest connected set of rules (the table)."""
    segs = [("v", s) for s in vs] + [("h", s) for s in hs]
    if len(vs) < 3 or len(hs) < 2:
        return None
    parent = list(range(len(segs)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def touch(a: tuple[str, _Seg], b: tuple[str, _Seg]) -> bool:
        (ka, sa), (kb, sb) = a, b
        if ka == kb:
            return False
        v, h = (sa, sb) if ka == "v" else (sb, sa)
        return h.lo - 2 <= v.pos <= h.hi + 2 and v.lo - 2 <= h.pos <= v.hi + 2

    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            if touch(segs[i], segs[j]):
                parent[find(i)] = find(j)
    groups: dict[int, list[tuple[str, _Seg]]] = {}
    for i, s in enumerate(segs):
        groups.setdefault(find(i), []).append(s)
    best, best_area = None, 0.0
    for members in groups.values():
        xs = [s.pos for k, s in members if k == "v"]
        if len({round(x) for x in xs}) < 3:
            continue
        x0 = min(min(s.lo for k, s in members if k == "h"), min(xs))
        x1 = max(max(s.hi for k, s in members if k == "h"), max(xs))
        y0 = min(min(s.lo for k, s in members if k == "v"), min(s.pos for k, s in members if k == "h"))
        y1 = max(max(s.hi for k, s in members if k == "v"), max(s.pos for k, s in members if k == "h"))
        area = (x1 - x0) * (y1 - y0)
        if area > best_area:
            best, best_area = (x0, y0, x1, y1), area
    return best


def _grid(vs: list[_Seg], hs: list[_Seg], box) -> tuple[list[float], list[float], list[_Seg]]:
    x0, y0, x1, y1 = box
    inside_v = [s for s in vs if x0 - 2 <= s.pos <= x1 + 2 and s.hi >= y0 - 2 and s.lo <= y1 + 2]
    inside_h = [s for s in hs if y0 - 2 <= s.pos <= y1 + 2 and s.hi >= x0 - 2 and s.lo <= x1 + 2]
    cols = [pos for pos, ivs in _cluster(inside_v) if _coverage(ivs) >= _MIN_COVERAGE * (y1 - y0)]
    rows = [pos for pos, ivs in _cluster(inside_h) if _coverage(ivs) >= _MIN_COVERAGE * (x1 - x0)]
    return cols, rows, inside_v


# --- text --------------------------------------------------------------------------- #
def _lines(page) -> list[_Line]:
    """Word-level tokens with their direction.

    PyMuPDF merges text that shares a baseline into one "line" even across table
    cells ("Screen." and "Treatment" from neighbouring cells came back as one line),
    so tokens are rebuilt from characters and split at spaces and at gaps wider than
    half the font size.
    """
    out: list[_Line] = []
    for block in page.get_text("rawdict")["blocks"]:
        for ln in block.get("lines", []):
            dx, dy = ln["dir"]
            rotated = abs(dx) < 0.7
            reads_up = dy < 0
            for span in ln["spans"]:
                size = span.get("size", 8.0)
                token: list[dict] = []

                def flush() -> None:
                    if token:
                        text = "".join(c["c"] for c in token)
                        xs0 = min(c["bbox"][0] for c in token)
                        ys0 = min(c["bbox"][1] for c in token)
                        xs1 = max(c["bbox"][2] for c in token)
                        ys1 = max(c["bbox"][3] for c in token)
                        out.append(_Line(text, (xs0, ys0, xs1, ys1), rotated, reads_up))
                        token.clear()

                for ch in span["chars"]:
                    if ch["c"].isspace():
                        flush()
                        continue
                    if token:
                        prev = token[-1]["bbox"]
                        cur = ch["bbox"]
                        gap = (prev[1] - cur[3]) if rotated and reads_up else                               (cur[1] - prev[3]) if rotated else (cur[0] - prev[2])
                        if gap > 0.5 * size:
                            flush()
                    token.append(ch)
                flush()
    return out


def _cell_lines(lines: Iterable[_Line], x0: float, x1: float, y0: float, y1: float) -> list[_Line]:
    return [ln for ln in lines if x0 <= ln.cx <= x1 and y0 <= ln.cy <= y1]


def _visual_lines(tokens: list[_Line]) -> list[str]:
    """Horizontal tokens -> lines of text (top to bottom, left to right)."""
    rows: list[list[_Line]] = []
    for tok in sorted((t for t in tokens if not t.rotated), key=lambda t: t.cy):
        if rows and abs(rows[-1][0].cy - tok.cy) <= 0.6 * max(tok.bbox[3] - tok.bbox[1], 4.0):
            rows[-1].append(tok)
        else:
            rows.append([tok])
    return [" ".join(t.text for t in sorted(r, key=lambda t: t.cx)) for r in rows]


def _rotated_lines(tokens: list[_Line]) -> list[str]:
    """Rotated tokens -> lines (stacked side by side), each read along its direction."""
    rot = [t for t in tokens if t.rotated]
    if not rot:
        return []
    up = rot[0].reads_up
    columns: list[list[_Line]] = []
    for tok in sorted(rot, key=lambda t: t.cx):
        if columns and abs(columns[-1][0].cx - tok.cx) <= 3.0:
            columns[-1].append(tok)
        else:
            columns.append([tok])
    if not up:
        columns.reverse()
    return [" ".join(t.text for t in sorted(col, key=lambda t: t.cy, reverse=up)) for col in columns]


def _join(lines: list[_Line]) -> str:
    """Cell text: horizontal lines top to bottom, then rotated lines in stacking order."""
    parts = _visual_lines(lines) + _rotated_lines(lines)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _edges_in_band(t: _Table, y0: float, y1: float) -> list[float]:
    """Column edges that actually pass through the band (a merged cell has fewer)."""
    mid = (y0 + y1) / 2
    present = []
    for i, x in enumerate(t.col_edges):
        if i in (0, len(t.col_edges) - 1):
            present.append(x)
            continue
        if any(abs(s.pos - x) <= _TOL and s.lo <= mid <= s.hi for s in t.vertical):
            present.append(x)
    return present


def _row_is_group(t: _Table, r: int) -> bool:
    y0, y1 = t.row_edges[r], t.row_edges[r + 1]
    return len(_edges_in_band(t, y0, y1)) == 2 and bool(
        _cell_lines(t.lines, t.col_edges[0], t.col_edges[-1], y0, y1))


def _row_has_mark(t: _Table, r: int, first_visit_col: int, last_visit_col: int) -> bool:
    y0, y1 = t.row_edges[r], t.row_edges[r + 1]
    for c in range(first_visit_col, last_visit_col):
        cell = _cell_lines(t.lines, t.col_edges[c], t.col_edges[c + 1], y0, y1)
        if any(not ln.rotated and _MARK.match(ln.text) for ln in cell):
            return True
    return False


# --- assembly ----------------------------------------------------------------------- #
def _norm_epoch(text: str) -> str:
    for pattern, name in _EPOCH_NAMES:
        if pattern.match(text.strip()):
            return name
    return text.strip()


def _split_label(parts: list[str]) -> tuple[str, str]:
    """``(visit name, window text)`` from a column's header fragments."""
    name = [p for p in parts if not _WINDOW.match(p)]
    window = [p for p in parts if _WINDOW.match(p) and not re.match(r"^\d+\s*days?\)?$", p, re.I)]
    return " ".join(name).strip(), " ".join(window).strip()


def _detect_notes_column(t: _Table, first_visit_col: int, header_rows: int) -> int:
    """Index (into columns) of the notes column, or ``len(columns)`` if there is none."""
    n_cols = len(t.col_edges) - 1
    top, bottom = t.row_edges[0], t.row_edges[max(1, header_rows)]
    last = n_cols - 1
    text = _join(_cell_lines(t.lines, t.col_edges[last], t.col_edges[last + 1], top, bottom))
    widths = sorted(t.col_edges[i + 1] - t.col_edges[i] for i in range(first_visit_col, n_cols))
    median = widths[len(widths) // 2] if widths else 0
    wide = (t.col_edges[last + 1] - t.col_edges[last]) > 2.5 * max(median, 1)
    return last if ("note" in text.lower() or wide) and last > first_visit_col else n_cols


def _build_table(page, number: int) -> _Table | None:
    vs, hs = _rules(page)
    box = _table_box(vs, hs)
    if box is None:
        return None
    cols, rows, inside_v = _grid(vs, hs, box)
    if len(cols) < 4 or len(rows) < 3:
        return None
    lines = [ln for ln in _lines(page)
             if box[0] - 2 <= ln.cx <= box[2] + 2 and box[1] - 2 <= ln.cy <= box[3] + 2]
    return _Table(number, cols, rows, inside_v, lines)


def _body_start(t: _Table, notes_col: int) -> int:
    n_rows = len(t.row_edges) - 1
    for r in range(1, n_rows):
        if _row_is_group(t, r) or _row_has_mark(t, r, 1, notes_col):
            return r
    return n_rows


def _same_columns(a: list[float], b: list[float]) -> bool:
    return len(a) == len(b) and all(abs(x - y) <= 3.0 for x, y in zip(a, b, strict=True))


@dataclass
class _Parsed:
    visits: list[str]
    timings: list[str]
    epochs: list[str]
    rows: list[tuple[str, dict[int, str]]]      # (label, {visit index: mark})


def _parse_table_pages(tables: list[_Table]) -> _Parsed:
    first = tables[0]
    n_cols = len(first.col_edges) - 1
    # The header is the rows above the first group/mark row; decide the notes column
    # from a provisional two-row header, then re-derive the body start.
    notes_col = _detect_notes_column(first, 1, 2)
    first.body_start = _body_start(first, notes_col)
    notes_col = _detect_notes_column(first, 1, max(1, first.body_start))
    first.body_start = _body_start(first, notes_col)
    visit_cols = list(range(1, notes_col))

    # ---- header bands -> epochs, visit labels and unit hints
    epoch_by_col: dict[int, str] = {}
    unit_by_col: dict[int, tuple[str, str]] = {}
    label_parts: dict[int, list[str]] = {c: [] for c in visit_cols}
    for r in range(first.body_start):
        y0, y1 = first.row_edges[r], first.row_edges[r + 1]
        edges = _edges_in_band(first, y0, y1)
        for i in range(len(edges) - 1):
            ex0, ex1 = edges[i], edges[i + 1]
            covered = [c for c in visit_cols
                       if first.col_edges[c] >= ex0 - _TOL and first.col_edges[c + 1] <= ex1 + _TOL]
            if not covered:
                continue
            cell = _cell_lines(first.lines, ex0, ex1, y0, y1)
            text = _join(cell)
            if not text:
                continue
            unit = _UNIT_HINT.search(text)
            if unit:
                for c in covered:
                    unit_by_col.setdefault(c, (unit.group(1).capitalize(), (unit.group(2) or "").strip()))
            if r == 0:
                for c in covered:
                    epoch_by_col.setdefault(c, _norm_epoch(text))
                if len(covered) == 1:
                    label_parts[covered[0]].append("\x00" + text)
            elif len(covered) == 1:
                rotated = " ".join(_rotated_lines(cell))
                horizontal = " ".join(_visual_lines(cell))
                label_parts[covered[0]] += [p for p in (rotated, horizontal) if p]
    visits, timings, epochs = [], [], []
    last_epoch = ""
    for c in visit_cols:
        parts = label_parts[c]
        primary = [p for p in parts if not p.startswith("\x00")]
        fallback = [p[1:] for p in parts if p.startswith("\x00")]
        name, window = _split_label(primary or fallback)
        if not name:
            name, _ = _split_label(fallback)
        if re.fullmatch(r"\d+(?:\.\d+)?", name or "") and c in unit_by_col:
            unit_name, unit_window = unit_by_col[c]        # "8" under "Week (+/- 7 days)" -> "Week 8"
            name = f"{unit_name} {name}"
            window = window or unit_window
        epoch = epoch_by_col.get(c, "")
        if not epoch or (_EXTENDS_PREVIOUS.match(epoch) and last_epoch):
            epoch = last_epoch or epoch
        last_epoch = epoch or last_epoch
        visits.append(name or f"V{c}")
        timings.append(f"{name} {window}".strip() if name else f"V{c}")
        epochs.append(epoch)

    # ---- body rows over all pages of this table
    header_signatures = {
        re.sub(r"\W+", "", _join(_cell_lines(first.lines, first.col_edges[0], first.col_edges[1],
                                             first.row_edges[r], first.row_edges[r + 1])).lower())
        for r in range(first.body_start)}
    rows: list[tuple[str, dict[int, str]]] = []
    for t in tables:
        start = first.body_start if t is first else 0
        for r in range(start, len(t.row_edges) - 1):
            y0, y1 = t.row_edges[r], t.row_edges[r + 1]
            label = _join(_cell_lines(t.lines, t.col_edges[0], t.col_edges[1], y0, y1))
            signature = re.sub(r"\W+", "", label.lower())
            if t is not first and signature in header_signatures:
                continue                                    # repeated header row
            if t is not first and not label and not any(
                    _MARK.match(ln.text) for ln in _cell_lines(
                        t.lines, t.col_edges[1], t.col_edges[notes_col], y0, y1)):
                continue                                    # empty header remnant
            marks: dict[int, str] = {}
            if not _row_is_group(t, r):
                for vi, c in enumerate(visit_cols):
                    cell = _cell_lines(t.lines, t.col_edges[c], t.col_edges[c + 1], y0, y1)
                    hit = next((ln.text for ln in cell if not ln.rotated and _MARK.match(ln.text)), None)
                    if hit:
                        marks[vi] = hit
            if label or marks:
                rows.append((label, marks))
    return _Parsed(visits, timings, epochs, rows)


def read_soa_geometry(pdf_path: str | Path, pages: list[int] | None = None) -> SoAGrid | None:
    """Read a Schedule of Activities from the ruling lines of ``pages``.

    Args:
        pdf_path: The protocol PDF.
        pages: 1-indexed pages of the schedule-of-activities section. ``None``
            reads every page (the caller normally passes the section's pages).

    Returns:
        A ``SoAGrid(method="geometry")``, or ``None`` when no ruled table with
        visit columns is found (never a guess).
    """
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    try:
        wanted = sorted(set(pages)) if pages else range(1, doc.page_count + 1)
        tables: list[_Table] = []
        for pno in wanted:
            if 1 <= pno <= doc.page_count:
                t = _build_table(doc[pno - 1], pno)
                if t is not None:
                    tables.append(t)
    finally:
        doc.close()
    if not tables:
        return None

    # Consecutive pages with the same columns are one table; a new column layout starts another.
    groups: list[list[_Table]] = []
    for t in tables:
        if groups and _same_columns(groups[-1][0].col_edges, t.col_edges):
            groups[-1].append(t)
        else:
            groups.append([t])

    visits: list[str] = []
    timings: list[str] = []
    epochs: list[str] = []
    activities: list[str] = []
    index_of: dict[str, int] = {}
    cells: set[tuple[int, int]] = set()
    for group in groups:
        parsed = _parse_table_pages(group)
        offset = len(visits)
        visits += parsed.visits
        timings += parsed.timings
        epochs += parsed.epochs
        for label, marks in parsed.rows:
            key = re.sub(r"\W+", "", label.lower()) or f"row{len(activities)}"
            if key not in index_of:
                index_of[key] = len(activities)
                activities.append(label)
            for vi in marks:
                cells.add((index_of[key], offset + vi))
    if not visits or not activities:
        return None
    return SoAGrid(method="geometry", epochs=epochs, visits=visits, timings=timings,
                   activities=activities, cells=cells)
