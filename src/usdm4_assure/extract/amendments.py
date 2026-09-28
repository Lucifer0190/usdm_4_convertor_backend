"""Amendments — section-level diff of two protocol versions (task 6.2).

Given the prior and the amended version of a protocol, every section is
compared word-for-word. Each difference becomes a :class:`SectionChange`
carrying:

* a **description** built from the actual changed words, with a verbatim
  quote grounding it in the version that contains them (the new version,
  or the old one for a pure deletion) — so a reviewer can click to it;
* the **rationale**, taken from the amended version's own amendment summary
  (the section graph's ``amendment_history`` sections) — the item that names
  the changed section's number or title — also quote-grounded. A change the
  summary does not explain is reported, not given an invented reason;
* the extraction **domains** the change touches (by section type), which is
  what a downstream re-extraction needs to know.

Sections are matched by title, not number, so an inserted section that
renumbers everything after it does not read as a wholesale rewrite. Running
page furniture (headers and footers repeated across pages — which carry the
version number and so always differ between versions) is removed before
comparison; the amendment summary and table of contents are not compared.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from usdm4_assure.contracts import Block, Document, Finding, FindingKind, Quote, Severity
from usdm4_assure.ground.quote import resolve_quote
from usdm4_assure.sections.graph import Section, SectionGraph

DOMAIN = "amendments"
FURNITURE_PAGES = 3          # identical text on this many pages is a running header/footer
CONTEXT_WORDS = 4            # words of unchanged context around a changed span
MAX_SPANS = 3                # changed spans spelled out per section description
SHORT_ITEM_WORDS = 12        # a summary item this short is a table's section cell

_TOKEN = re.compile(r"\w+")
_LEADING_NUMBER = re.compile(r"^\s*(?:section\s+)?\d+(?:\.\d+)*\.?\s*", re.IGNORECASE)
_PAGE_NUMBER = re.compile(r"(?i)^\s*(?:page\s*)?\d+(?:\s*(?:of|/)\s*\d+)?\s*$")
_SKIP_SUBTYPES = frozenset({"amendment_history", "table_of_contents"})
_DOMAINS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "header": ("metadata",), "summary": ("metadata", "design"), "design": ("design",),
    "interventions": ("design",), "population": ("eligibility",),
    "science": ("objectives", "estimands"), "statistics": ("estimands",),
    "assessments": ("soa",),
}


@dataclass(frozen=True)
class SectionChange:
    kind: str                         # modified | added | removed
    number: str
    title: str                        # without its number
    section_type: str | None
    description: str
    quote: Quote | None               # grounds the change in the version containing it
    quote_version: str                # "new" | "old"
    rationale: str
    rationale_quote: Quote | None
    affected_domains: tuple[str, ...]
    similarity: float                 # word-sequence ratio, 1.0 = identical

    @property
    def section_ref(self) -> str:
        return f"{self.number} {self.title}".strip()


@dataclass
class AmendmentDiff:
    changes: list[SectionChange] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    unchanged: int = 0


@dataclass(frozen=True)
class _SectionText:
    section: Section | None
    number: str
    title: str
    text: str


def _strip_number(title: str) -> str:
    return _LEADING_NUMBER.sub("", title).strip()


def _norm_title(title: str) -> str:
    return " ".join(_TOKEN.findall(_strip_number(title).lower()))


def _furniture(doc: Document) -> set[str]:
    pages: dict[str, set[int]] = {}
    for b in doc.blocks:
        pages.setdefault(" ".join(b.text.split()), set()).add(b.page)
    return {t for t, p in pages.items() if len(p) >= FURNITURE_PAGES}


def _content_blocks(doc: Document) -> list[Block]:
    furniture = _furniture(doc)
    return [b for b in doc.blocks
            if " ".join(b.text.split()) not in furniture and not _PAGE_NUMBER.match(b.text)]


def section_texts(doc: Document, graph: SectionGraph) -> dict[str, _SectionText]:
    """Comparable text per section, keyed by normalized title (number stripped)."""
    by_id: dict[int, list[str]] = {}
    for b in _content_blocks(doc):
        s = graph.block_section(b)
        if s is not None and s.title != b.text.strip():     # the heading itself isn't content
            by_id.setdefault(id(s), []).append(b.text)
    out: dict[str, _SectionText] = {}
    for s in graph.sections:
        if s.section_subtype in _SKIP_SUBTYPES or s.authority_surface == "title_identity":
            continue
        key = _norm_title(s.title) or s.number
        if key in out:                                       # duplicate title: disambiguate
            key = f"{key} [{s.number or len(out)}]"
        out[key] = _SectionText(s, s.number, _strip_number(s.title),
                                "\n".join(by_id.get(id(s), [])))
    return out


def _tokens(text: str) -> list[re.Match]:
    return list(_TOKEN.finditer(text))


def _excerpt(text: str, toks: list[re.Match], i: int, j: int) -> str:
    """Verbatim text covering tokens [i, j) plus a little unchanged context."""
    if not toks:
        return ""
    lo, hi = max(0, i - CONTEXT_WORDS), min(len(toks), max(j, i + 1) + CONTEXT_WORDS)
    return " ".join(text[toks[lo].start():toks[hi - 1].end()].split())


def _describe(old: str, new: str) -> tuple[str, str, float]:
    """``(description, new-version grounding excerpt, similarity)`` for a modified section.

    The excerpt is always from the *new* version — a reviewer checks the
    current text. It covers the first changed span that has new words, or,
    if every change is a deletion, the context at the first deletion point.
    """
    ot, nt = _tokens(old), _tokens(new)
    sm = SequenceMatcher(None, [t.group().lower() for t in ot], [t.group().lower() for t in nt],
                         autojunk=False)
    ops = [op for op in sm.get_opcodes() if op[0] != "equal"]
    spans = []
    for tag, i1, i2, j1, j2 in ops[:MAX_SPANS]:
        before = " ".join(t.group() for t in ot[i1:i2])
        after = " ".join(t.group() for t in nt[j1:j2])
        spans.append({"replace": f"'{before}' -> '{after}'", "insert": f"added '{after}'",
                      "delete": f"removed '{before}'"}[tag])
    anchor = next((op for op in ops if op[0] != "delete"), ops[0] if ops else None)
    excerpt = _excerpt(new, nt, anchor[3], anchor[4]) if anchor else ""
    more = f" (+{len(ops) - MAX_SPANS} more)" if len(ops) > MAX_SPANS else ""
    return "; ".join(spans) + more, excerpt, sm.ratio()


def _summary_items(doc: Document, graph: SectionGraph) -> list[str]:
    """The amended version's amendment-summary paragraphs, in reading order."""
    items = []
    for b in _content_blocks(doc):
        s = graph.block_section(b)
        if s is not None and s.section_subtype == "amendment_history" and b.text != s.title:
            items.append(" ".join(b.text.split()))
    return items


def _rationale(number: str, title: str, items: list[str]) -> str:
    num_re = (re.compile(rf"(?<![\d.]){re.escape(number)}(?![\d])") if number else None)
    title_norm = _norm_title(title)
    for i, item in enumerate(items):
        hit = (num_re is not None and num_re.search(item)) or (
            len(title_norm.split()) >= 2 and title_norm in _norm_title(item))
        if hit:
            if len(item.split()) <= SHORT_ITEM_WORDS and i + 1 < len(items):
                return f"{item} {items[i + 1]}"              # a table row split across cells
            return item
    return ""


def _ground(doc: Document, text: str) -> Quote | None:
    return resolve_quote(doc, text) if text else None


def diff_versions(old_doc: Document, new_doc: Document, old_graph: SectionGraph,
                  new_graph: SectionGraph) -> AmendmentDiff:
    """Section-level changes from ``old_doc`` to ``new_doc``."""
    diff = AmendmentDiff()
    old_s, new_s = section_texts(old_doc, old_graph), section_texts(new_doc, new_graph)
    if not old_s or not new_s:
        diff.findings.append(Finding(FindingKind.COMPLETENESS, Severity.WARNING, DOMAIN,
                                     "No section graph for one of the versions; the diff is "
                                     "document-level and cannot attribute changes to sections."))
        key = "(whole document)"
        old_s = {key: _SectionText(None, "", key, "\n".join(b.text for b in _content_blocks(old_doc)))}
        new_s = {key: _SectionText(None, "", key, "\n".join(b.text for b in _content_blocks(new_doc)))}
    items = _summary_items(new_doc, new_graph)

    for key in list(new_s) + [k for k in old_s if k not in new_s]:
        old, new = old_s.get(key), new_s.get(key)
        ref = new or old
        if old is not None and new is not None:
            description, excerpt, ratio = _describe(old.text, new.text)
            if ratio == 1.0:
                diff.unchanged += 1
                continue
            kind, version = "modified", "new"
        elif new is not None:
            description, excerpt, version, ratio = (
                "Section added.", " ".join(new.text.split()[:30]), "new", 0.0)
            kind = "added"
        else:
            description, excerpt, version, ratio = (
                "Section removed.", " ".join(old.text.split()[:30]), "old", 0.0)
            kind = "removed"
        rationale = _rationale(ref.number, ref.title, items)
        stype = ref.section.section_type if ref.section is not None else None
        change = SectionChange(
            kind=kind, number=ref.number, title=ref.title or key, section_type=stype,
            description=description,
            quote=_ground(new_doc if version == "new" else old_doc, excerpt),
            quote_version=version, rationale=rationale,
            rationale_quote=_ground(new_doc, rationale),
            affected_domains=_DOMAINS_BY_TYPE.get(stype or "", ()), similarity=round(ratio, 4))
        diff.changes.append(change)
        if not rationale:
            diff.findings.append(Finding(
                FindingKind.COMPLETENESS, Severity.WARNING, DOMAIN,
                f"Change to section '{change.section_ref}' ({kind}) has no rationale in the "
                "amended version's amendment summary.", field=change.section_ref))
    return diff


def diff_pdfs(old_pdf, new_pdf) -> tuple[AmendmentDiff, Document, Document]:
    """Ingest both versions, build their section graphs, and diff them."""
    from usdm4_assure.ingest.pdf import ingest
    from usdm4_assure.sections.graph import build_graph
    old_doc, new_doc = ingest(old_pdf), ingest(new_pdf)
    return (diff_versions(old_doc, new_doc, build_graph(old_doc, old_pdf),
                          build_graph(new_doc, new_pdf)), old_doc, new_doc)


def domains_touched(diff: AmendmentDiff) -> Counter:
    """How many changed sections touch each extraction domain."""
    return Counter(d for c in diff.changes for d in c.affected_domains)
