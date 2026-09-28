"""Extraction C5 — estimands (task 6.1, ICH E9(R1), DESIGN.md L4-L6).

An estimand is structured — population, variable (endpoint), treatment,
intercurrent events each with a handling strategy, and a population-level
summary — so it does not fit the flat ``{field, value, quote}`` shards. Three
independent members read it, each grounding every attribute to a verbatim
quote:

* a **deterministic** label parser ("Population: ...", "Intercurrent events:
  ...") — only accepts a group that carries an estimand's hallmarks (a summary
  measure or intercurrent events), so a synopsis "Population:" line never
  becomes a phantom estimand;
* the **hard_reasoning** role (frontier, escalation tier);
* the **extract_alt** role (a different model family), so agreement between
  the two LLMs is a cross-family signal, not one model agreeing with itself.

Members' estimands are aligned by attribute similarity, then every scalar
attribute is flattened to a field (``estimand1.summary_measure``) and pushed
through the same :func:`usdm4_assure.assure.assure` as every other domain —
grounding hard gate, agreement, verifier, triage — rather than a bespoke
confidence rule. Intercurrent events are reconciled as a set: an event with no
resolvable quote is dropped (and reported), never kept on trust.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from usdm4_assure.assure import assure
from usdm4_assure.contracts import (
    AssuredField,
    Decision,
    Document,
    Finding,
    FindingKind,
    GroundedCandidate,
    Method,
    Quote,
    Severity,
)
from usdm4_assure.ground.quote import resolve_quote
from usdm4_assure.llm.base import LLM
from usdm4_assure.llm.config import model_for
from usdm4_assure.llm.two_pass import run_two_pass, template_hash

DOMAIN = "estimands"
PROMPT_ID = "c5_estimands"
ATTRIBUTES = ("population", "variable", "treatment", "summary_measure")
STRATEGIES = {  # canonical ICH E9(R1) name -> pattern
    "treatment policy": r"treatment[- ]policy",
    "hypothetical": r"hypothetical",
    "composite": r"composite",
    "while on treatment": r"while[- ]on[- ]treatment",
    "principal stratum": r"principal[- ]strat",
}
ALIGN_THRESHOLD = 0.4   # token Jaccard for "same estimand" across members
ICE_THRESHOLD = 0.5     # token Jaccard for "same intercurrent event"

_LABELS = {
    "population": r"(?:target\s+|analysis\s+)?population",
    "variable": r"variable(?:\s+of\s+interest)?|endpoint",
    "treatment": r"treatment(?:\s+conditions?)?|interventions?",
    "intercurrent_events": r"intercurrent\s+events?(?:\s+and\s+(?:their\s+)?strateg(?:y|ies))?",
    "summary_measure": r"(?:population[- ]level\s+)?summary(?:\s+measure)?",
}
_LABEL_RE = re.compile(
    r"(?im)^[ \t]*(?:[-•*]\s*)?(?:"
    + "|".join(f"(?P<{k}>{v})" for k, v in _LABELS.items()) + r")[ \t]*:[ \t]*")
_HEADING_RE = re.compile(
    r"(?im)^[ \t]*((?:(?:primary|secondary|key[ \t]+secondary|exploratory|supportive)[ \t]+)?"
    r"estimand\b[^\n:]{0,40}?)[ \t]*:?[ \t]*$")
_WORD = re.compile(r"\w+")
_MAX_VALUE = 1200


# --- member output ------------------------------------------------------------ #
@dataclass(frozen=True)
class GroundedValue:
    value: str
    quote: Quote


@dataclass(frozen=True)
class IceCandidate:
    text: str
    strategy: str      # canonical STRATEGIES key, or "" if the text names none
    quote: Quote


@dataclass
class EstimandCandidate:
    """One member's reading of one estimand."""
    method: Method
    model_id: str | None = None
    prompt_hash: str | None = None
    name: str = ""
    attributes: dict[str, GroundedValue] = field(default_factory=dict)
    intercurrent_events: list[IceCandidate] = field(default_factory=list)


def token_jaccard(a: str, b: str) -> float:
    ta, tb = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def canonical_strategy(text: str) -> str:
    return next((name for name, pat in STRATEGIES.items()
                 if re.search(pat, text, re.IGNORECASE)), "")


def _ground(doc: Document, value: str, quote_text: str | None) -> Quote:
    """A missing quote is a failed one (DESIGN.md L5) — never a free pass."""
    return resolve_quote(doc, quote_text) if quote_text else Quote.failed(value)


# --- deterministic member ------------------------------------------------------- #
def _split_ices(raw: str) -> list[str]:
    parts = re.split(r"[;\n]|(?:^|\s)[•*-]\s+", raw)
    return [p.strip(" .") for p in parts if p and len(p.strip(" .")) > 3]


def _ice_from_item(doc: Document, item: str) -> IceCandidate:
    strategy = canonical_strategy(item)
    text = item
    if strategy:
        text = re.split(r"\s*(?::|—|–| - |\(|\bhandled\b|\busing\b)\s*", item,
                        maxsplit=1)[0] or item
    return IceCandidate(text=text.strip(), strategy=strategy, quote=_ground(doc, item, item))


def _groups(text: str) -> list[tuple[str, dict[str, str]]]:
    """Sweep labels and estimand headings in reading order into attribute groups.

    A heading, or a label repeating within the current group, starts a new
    group. A value runs to the next label or heading; every attribute but the
    intercurrent-event list is one paragraph (ingest joins blocks with "\\n").
    """
    events = sorted([(m.start(), m.end(), m.lastgroup, "") for m in _LABEL_RE.finditer(text)]
                    + [(m.start(), m.end(), None, m.group(1).strip())
                       for m in _HEADING_RE.finditer(text)])
    groups: list[tuple[str, dict[str, str]]] = []
    current: dict[str, str] = {}
    name = ""
    for i, (_start, end, label, heading) in enumerate(events):
        if label is None or label in current:
            if current:
                groups.append((name, current))
            current = {}
            name = heading if label is None else ""
            if label is None:
                continue
        nxt = events[i + 1][0] if i + 1 < len(events) else len(text)
        value = text[end:nxt]
        if label != "intercurrent_events":
            value = value.split("\n", 1)[0]
        current[label] = value.strip()[:_MAX_VALUE]
    if current:
        groups.append((name, current))
    return groups


def extract_deterministic(doc: Document) -> list[EstimandCandidate]:
    groups = _groups(doc.full_text)

    out = []
    for gname, g in groups:
        hallmark = "summary_measure" in g or "intercurrent_events" in g
        if not hallmark or len(g) < 3:
            continue
        cand = EstimandCandidate(method=Method.DET_TEXT, name=gname)
        for attr in ATTRIBUTES:
            if g.get(attr):
                value = re.sub(r"\s+", " ", g[attr])
                cand.attributes[attr] = GroundedValue(value, _ground(doc, value, g[attr]))
        cand.intercurrent_events = [_ice_from_item(doc, item)
                                    for item in _split_ices(g.get("intercurrent_events", ""))]
        out.append(cand)
    return out


# --- LLM members ---------------------------------------------------------------- #
def _model_id(llm: LLM) -> str | None:
    if getattr(llm, "model", None):
        return llm.model
    role = getattr(llm, "role", None)
    return model_for(role) if role else getattr(llm, "name", None)


def extract_llm(doc: Document, llm: LLM) -> list[EstimandCandidate] | None:
    """One LLM member's estimands; ``None`` if the member did not run."""
    items = run_two_pass(llm, PROMPT_ID, doc.full_text)
    if items is None:
        return None
    phash, model_id = template_hash(PROMPT_ID), _model_id(llm)
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cand = EstimandCandidate(method=Method.LLM_FRONTIER, model_id=model_id,
                                 prompt_hash=phash, name=str(it.get("name") or ""))
        for attr in ATTRIBUTES:
            v = it.get(attr)
            if isinstance(v, dict) and v.get("value"):
                value = str(v["value"]).strip()
                cand.attributes[attr] = GroundedValue(value, _ground(doc, value, v.get("quote")))
        for ice in it.get("intercurrent_events") or []:
            if isinstance(ice, dict) and ice.get("text"):
                text = str(ice["text"]).strip()
                cand.intercurrent_events.append(IceCandidate(
                    text=text, strategy=canonical_strategy(str(ice.get("strategy") or "")),
                    quote=_ground(doc, text, ice.get("quote"))))
        if cand.attributes:
            out.append(cand)
    return out


# --- reconciliation ------------------------------------------------------------- #
@dataclass
class AssuredIntercurrentEvent:
    text: str
    strategy: str
    quote: Quote
    support: int        # members that reported this event
    n_members: int      # members that reported this estimand at all


@dataclass
class AssuredEstimand:
    index: int
    name: str
    attributes: dict[str, AssuredField]
    intercurrent_events: list[AssuredIntercurrentEvent]

    def value(self, attr: str) -> str | None:
        """The attribute's value, unless triage BLOCKed it."""
        f = self.attributes.get(attr)
        return f.value if f is not None and f.decision is not Decision.BLOCK else None

    @property
    def usable(self) -> bool:
        """Enough to assemble: a variable to link and a summary measure."""
        return bool(self.value("variable") and self.value("summary_measure"))


@dataclass
class EstimandsExtract:
    estimands: list[AssuredEstimand] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    n_members: int = 0

    def assured_fields(self) -> list[AssuredField]:
        return [f for e in self.estimands for f in e.attributes.values()]


def _match_score(a: EstimandCandidate, b: EstimandCandidate) -> float:
    shared = [k for k in ("variable", "summary_measure", "population")
              if k in a.attributes and k in b.attributes]
    return max((token_jaccard(a.attributes[k].value, b.attributes[k].value) for k in shared),
               default=0.0)


def align(members: Sequence[Sequence[EstimandCandidate]]) -> list[list[EstimandCandidate]]:
    """Slots of same-estimand candidates, at most one per member per slot."""
    slots: list[list[EstimandCandidate]] = []
    for cands in members:
        taken: set[int] = set()
        for cand in cands:
            best, best_score = None, ALIGN_THRESHOLD
            for s_i, slot in enumerate(slots):
                if s_i in taken:
                    continue
                score = max(_match_score(cand, c) for c in slot)
                if score >= best_score:
                    best, best_score = s_i, score
            if best is None:
                slots.append([cand])
                best = len(slots) - 1
            else:
                slots[best].append(cand)
            taken.add(best)
    return slots


def _reconcile_ices(slot: list[EstimandCandidate], index: int
                    ) -> tuple[list[AssuredIntercurrentEvent], list[Finding]]:
    groups: list[list[IceCandidate]] = []
    for cand in slot:
        for ice in cand.intercurrent_events:
            g = next((g for g in groups if token_jaccard(g[0].text, ice.text) >= ICE_THRESHOLD), None)
            if g is None:
                groups.append([ice])
            else:
                g.append(ice)
    out, findings = [], []
    for g in groups:
        grounded = [i for i in g if i.quote.ok]
        if not grounded:
            findings.append(Finding(FindingKind.GROUNDING, Severity.WARNING, DOMAIN,
                                    f"Intercurrent event '{g[0].text[:80]}' dropped: no member's "
                                    "quote resolved in the protocol.",
                                    field=f"estimand{index}.intercurrent_events"))
            continue
        votes = Counter(i.strategy for i in g if i.strategy)
        strategy = votes.most_common(1)[0][0] if votes else ""
        if not strategy:
            findings.append(Finding(FindingKind.COMPLETENESS, Severity.WARNING, DOMAIN,
                                    f"Intercurrent event '{grounded[0].text[:80]}' has no "
                                    "stated handling strategy.",
                                    field=f"estimand{index}.intercurrent_events"))
        out.append(AssuredIntercurrentEvent(grounded[0].text, strategy, grounded[0].quote,
                                            support=len(g), n_members=len(slot)))
    return out, findings


def reconcile(members: Sequence[Sequence[EstimandCandidate]], doc: Document) -> EstimandsExtract:
    result = EstimandsExtract(n_members=len(members))
    for k, slot in enumerate(align(members), start=1):
        cands, fields = [], [f"estimand{k}.{a}" for a in ATTRIBUTES]
        for c in slot:
            for attr, gv in c.attributes.items():
                cands.append(GroundedCandidate(f"estimand{k}.{attr}", gv.value, c.method,
                                               quote=gv.quote, model_id=c.model_id,
                                               prompt_hash=c.prompt_hash, domain=DOMAIN))
        assured = assure(cands, doc, fields, domain=DOMAIN)
        ices, findings = _reconcile_ices(slot, k)
        name = next((c.name for c in slot if c.name), f"Estimand {k}")
        result.estimands.append(AssuredEstimand(
            index=k, name=name,
            attributes={a: f for a, f in zip(ATTRIBUTES, assured, strict=True)},
            intercurrent_events=ices))
        result.findings += findings
    # No estimands found is not itself a finding: pre-E9(R1) protocols define
    # none, and absence only becomes a gap against an expectation (completeness).
    return result


def extract_estimands(doc: Document, llms: Sequence[LLM] = ()) -> EstimandsExtract:
    """Deterministic member always; each available LLM member is added on top."""
    members = [extract_deterministic(doc)]
    for llm in llms:
        cands = extract_llm(doc, llm)
        if cands is not None:
            members.append(cands)
    return reconcile(members, doc)


def estimand_evidence(window_doc: Document, routed) -> Document:
    """Restrict a scoped window to estimand-bearing sections (science, statistics,
    ``estimands_table``) so the LLM's bounded context reaches the right text;
    the whole window when routing is off or finds no such section."""
    graph = getattr(routed, "graph", None)
    if graph is None or not graph.sections:
        return window_doc
    keep = []
    for b in window_doc.blocks:
        s = graph.block_section(b)
        if s is not None and (s.section_subtype == "estimands_table"
                              or s.section_type in ("science", "statistics")):
            keep.append(b)
    if not keep:
        return window_doc
    return Document(source=window_doc.source, blocks=keep,
                    full_text="\n".join(b.text for b in keep),
                    page_images=window_doc.page_images, chars=window_doc.chars)
