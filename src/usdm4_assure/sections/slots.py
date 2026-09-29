"""Section slots — narrow, clean evidence windows found by title meaning.

A real run showed what unscoped evidence costs: the eligibility extractor read
the table of contents and the amendment-history table, the phase regex read a
running footer ("Phase 1 2 3 4"), and the LLM only ever saw the first 12,000
characters of the whole protocol. The fix is to read each region from its own
section.

A **slot** is a canonical thing every protocol has (synopsis, schedule of
activities, objectives, inclusion / exclusion criteria, overall design,
interventions). It is found by the *meaning of the section title*, never by its
number: BMS and older Lilly protocols number the same sections differently
from Pfizer, and only the titles stay close.

Two pieces live here:

* :func:`strip_furniture` removes text that repeats on most pages (running
  headers and footers) before any extractor sees it;
* :func:`slot_document` returns the blocks of one or more slots as a small
  :class:`~usdm4_assure.contracts.Document`, or ``None`` when the slot is not
  found — never the whole document, so the caller can flag the gap instead of
  silently reading the wrong text.

A slot's span runs from its heading to the next section of the same or higher
level; nested matches (a "Table 1. Schedule of Activities" bookmark under
"1.3 Schedule of Activities") are merged rather than double counted. The
returned document shares the source's character geometry, so quote grounding
still resolves against the real page.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from usdm4_assure.contracts import Block, Document
from usdm4_assure.sections.graph import Section, SectionGraph

_INF = (10 ** 9, 0.0)


@dataclass(frozen=True)
class Slot:
    """A canonical protocol region and the title patterns that identify it.

    ``patterns`` are tried in order against the normalised title (numbering and
    trailing punctuation removed, lower-cased); the first pattern that matches
    any section wins, so list the most specific pattern first.
    """
    name: str
    patterns: tuple[str, ...]
    # Keep only matches within this many pages of the first match. A protocol's amendment
    # history repeats the *historic* schedules (Tables 16-18 on pages 184-211 of a 200-page
    # protocol) and those must not be read as the current one.
    cluster_pages: int | None = None


SLOTS: dict[str, Slot] = {s.name: s for s in (
    Slot("synopsis", (r"^(protocol )?synopsis$", r"^protocol summary$")),
    Slot("soa", (r"schedule of (activities|assessments|events)", r"^flow ?chart$",
                 r"time and events", r"study flow ?chart"), cluster_pages=15),
    Slot("objectives", (r"^objectives?,? (endpoints?,? )?(and )?(estimands?|endpoints?)",
                        r"^objectives?,? estimands?,? (and )?endpoints?",
                        r"^study objectives?$", r"^objectives?$")),
    Slot("inclusion", (r"^inclusion criteria$", r"^criteria for inclusion",
                       r"^subject eligibility$", r"^selection of (study )?(subjects|participants)")),
    Slot("exclusion", (r"^exclusion criteria$", r"^criteria for exclusion")),
    Slot("design", (r"^overall design$", r"^(overall )?study design$", r"^trial design$")),
    Slot("interventions", (r"^study interventions?(\(s\))? administered$",
                           r"^study treatments?( administered)?$", r"^study interventions?(\(s\))?$")),
)}


def _norm_title(title: str) -> str:
    t = re.sub(r"^\s*(?:appendix\s+\w+[:.]?\s*)?(?:\d+(?:\.\d+)*\.?\s+)", "", title.strip(),
               flags=re.IGNORECASE)
    return re.sub(r"[\s.:]+$", "", t).lower()


def _pos(s: Section) -> tuple[int, float]:
    return (s.page, s.y)


def _end_of(graph: SectionGraph, section: Section) -> tuple[int, float]:
    """Where ``section`` stops: the next section at the same or a higher level."""
    seen = False
    for other in graph.sections:
        if other is section:
            seen = True
            continue
        if seen and other.level <= section.level and _pos(other) > _pos(section):
            return _pos(other)
    return _INF


def find_sections(graph: SectionGraph, slot: str) -> list[Section]:
    """The outermost sections that are ``slot``, in reading order."""
    spec = SLOTS[slot]
    for pattern in spec.patterns:
        matched = [s for s in graph.sections if re.search(pattern, _norm_title(s.title))]
        if not matched:
            continue
        chosen: list[Section] = []
        for s in matched:
            if any(_pos(c) <= _pos(s) < _end_of(graph, c) for c in chosen):
                continue          # nested inside a section already chosen
            if spec.cluster_pages is not None and chosen and \
                    s.page - chosen[0].page > spec.cluster_pages:
                continue          # a historic copy far from the main one
            chosen.append(s)
        return chosen
    return []


def _in_span(b: Block, start: tuple[int, float], end: tuple[int, float]) -> bool:
    pos = (b.page, b.bbox[1])
    return (start[0], start[1] - 1.0) <= pos < (end[0], end[1] - 1.0)


def slot_blocks(doc: Document, graph: SectionGraph, slot: str) -> list[Block]:
    """Every block inside the slot's section span(s), in document order."""
    spans = [(_pos(s), _end_of(graph, s)) for s in find_sections(graph, slot)]
    return [b for b in doc.blocks if any(_in_span(b, a, z) for a, z in spans)]


def slot_pages(graph: SectionGraph, slot: str, page_count: int | None = None) -> list[int]:
    """Pages a slot covers (1-indexed). A span ending mid-page still includes that page."""
    pages: set[int] = set()
    for s in find_sections(graph, slot):
        end_page, end_y = _end_of(graph, s)
        last = page_count if end_page >= _INF[0] and page_count else end_page
        if end_page < _INF[0] and end_y <= 1.0:
            last = end_page - 1            # the next section starts at the top of its page
        pages.update(range(s.page, max(s.page, last or s.page) + 1))
    return sorted(pages)


@dataclass
class SlotWindow:
    """One or more slots' text as a small ``Document``, plus where it came from."""
    slots: tuple[str, ...]
    document: Document
    sections: list[Section]
    pages: list[int]


def slot_document(doc: Document, graph: SectionGraph, *slots: str,
                  front_pages: int = 0) -> SlotWindow | None:
    """The named slots' blocks as a scoped ``Document``.

    Args:
        doc: The (furniture-stripped) protocol document.
        graph: Its section graph.
        slots: Slot names from :data:`SLOTS`; blocks are returned in document order.
        front_pages: Also keep blocks from the first N pages (the title page,
            where study identity lives).

    Returns:
        ``None`` if *none* of the requested slots exists in the graph, so the
        caller must decide (and report) what to do instead of reading the whole
        protocol by accident.
    """
    sections = [s for name in slots for s in find_sections(graph, name)]
    if not sections:
        return None
    spans = [(_pos(s), _end_of(graph, s)) for s in sections]
    in_slots = [b for b in doc.blocks if any(_in_span(b, a, z) for a, z in spans)]
    kept = [b for b in doc.blocks if b.page <= front_pages or b in in_slots]
    # Pages that actually hold slot content (a span that ends mid-page does not
    # drag the whole next page in, which matters when the pages feed a table finder).
    pages = sorted({b.page for b in in_slots})
    scoped = Document(source=doc.source, blocks=kept,
                      full_text="\n".join(b.text for b in kept),
                      page_images=doc.page_images, chars=doc.chars)
    return SlotWindow(tuple(slots), scoped, sections, pages)


# --- page furniture ---------------------------------------------------------------- #
_FURNITURE_MIN_FRACTION = 0.5   # of all pages
_FURNITURE_MIN_PAGES = 5
_LONG_FURNITURE_CHARS = 25


def _furniture_key(b: Block) -> tuple[str, int]:
    text = re.sub(r"\d+", "#", b.text.lower())
    text = re.sub(r"\s+", " ", text).strip()
    # Long text that recurs is furniture wherever it sits (landscape pages put the
    # footer at a different height); short text must also share the vertical band.
    return text, (0 if len(text) >= _LONG_FURNITURE_CHARS else round(b.bbox[1] / 8.0))


def strip_furniture(doc: Document) -> Document:
    """Drop running headers/footers: identical text (page numbers ignored) at the
    same vertical position on most pages.

    The threshold is half the pages (and at least five), so a table header that
    merely repeats across an eight-page schedule of activities is kept.
    Character geometry is passed through untouched, so grounding is unaffected.
    """
    n_pages = len({b.page for b in doc.blocks})
    if n_pages == 0:
        return doc
    seen: dict[tuple[str, int], set[int]] = defaultdict(set)
    for b in doc.blocks:
        seen[_furniture_key(b)].add(b.page)
    floor = max(_FURNITURE_MIN_PAGES, _FURNITURE_MIN_FRACTION * n_pages)
    furniture = {k for k, pages in seen.items() if len(pages) >= floor and k[0]}
    kept = [b for b in doc.blocks if _furniture_key(b) not in furniture]
    return Document(source=doc.source, blocks=kept,
                    full_text="\n".join(b.text for b in kept),
                    page_images=doc.page_images, chars=doc.chars)
