"""Extraction C2 — study design skeleton (type, phase, intervention model, arms).

Deterministic parse of the synopsis/design prose. The arms parse is the novel bit:
a randomization sentence ("randomized 1:1:1 to A, B, or Placebo") yields the arm
list, and placebo/comparator language sets each arm's type.

Returns both:
  * scalar design FieldCandidates (studyType, interventionModel) for the Assurance layer
  * a structured arms list with a confidence + decision
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from usdm4_assure.assure.sanity import arm_name_ok
from usdm4_assure.contracts import Document, FieldCandidate, GroundedCandidate
from usdm4_assure.llm.base import LLM

DESIGN_FIELDS = ["studyType", "interventionModel", "armNames"]

_MODEL_RE = re.compile(
    r"\b(parallel|cross[- ]?over|single[- ]?group|factorial|sequential)\b", re.IGNORECASE)
_MODEL_NORM = {"parallel": "Parallel", "crossover": "Crossover",
               "cross-over": "Crossover", "cross over": "Crossover",
               "single-group": "Single Group", "single group": "Single Group",
               "factorial": "Factorial", "sequential": "Sequential"}


def normalize_model(value: str) -> str:
    """"Single-group" / "parallel design" / "Crossover" -> the canonical label, or the
    value unchanged when it names no known model (usdm4's encoder then reports it)."""
    m = _MODEL_RE.search(value or "")
    if not m:
        return value
    key = m.group(1).lower()
    return _MODEL_NORM.get(key, _MODEL_NORM.get(key.replace("-", " "), m.group(1).title()))


@dataclass
class DesignExtract:
    study_type: str = "Interventional"
    intervention_model: str | None = None
    arms: list[dict] = field(default_factory=list)
    arms_confidence: float = 0.0
    arms_decision: str = "review"
    arms_source: str = ""


def _arm_type(name: str) -> str:
    low = name.lower()
    if "placebo" in low:
        return "Placebo Comparator"
    if "active" in low or "comparator" in low or "standard of care" in low:
        return "Active Comparator"
    return "Experimental"


def arms_from_names(value: str) -> list[dict]:
    """Arm dicts from a ``"A; B"`` list (the ``armNames`` field), plausible names only."""
    seen, out = set(), []
    for raw in re.split(r"[;|]", value or ""):
        name = re.sub(r"\s+", " ", raw).strip(" .:;")
        if arm_name_ok(name) and name.lower() not in seen:
            seen.add(name.lower())
            out.append({"name": name, "type": _arm_type(name)})
    return out


# A bulleted/enumerated arm ("•   Arm A: (Investigational Arm; n ~ 280).", " Dose
# Level 1 (n ~ 25)."). Each bullet is its own sentence, sometimes with a running
# header/footer interleaved before the next one — the comma/period-bounded
# ``_parse_arms`` below only ever captures the first such bullet as a result.
_ARM_LABEL = re.compile(
    r"[•●■]\s*((?:Arm|Cohort|Dose\s+Level|Group|Part)\s+[A-Za-z0-9]+)\s*[:(]",
    re.IGNORECASE)


_ARM_KIND = re.compile(r"(Arm|Cohort|Dose\s+Level|Group|Part)", re.IGNORECASE)


def _bulleted_arms(text: str) -> tuple[list[dict], str]:
    """Arms named by an explicit bulleted label, wherever they appear in the text.

    A protocol can enumerate more than one thing this way (a dose-escalation "Dose
    Level 1/2" block, then a separate randomized-comparison "Arm A/B" block later) — only
    the first such family found is taken, so the two are never merged into one arm list.
    Requires at least 2 distinct labels, so one incidental "Part A" heading is not
    mistaken for the arm list.
    """
    seen, arms, kind = set(), [], None
    for m in _ARM_LABEL.finditer(text):
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        this_kind = _ARM_KIND.match(name).group(1).lower()
        if kind is None:
            kind = this_kind
        elif this_kind != kind:
            continue
        if arm_name_ok(name) and name.lower() not in seen:
            seen.add(name.lower())
            arms.append({"name": name, "type": _arm_type(name)})
    return (arms, "bulleted arm list") if len(arms) >= 2 else ([], "")


def _parse_arms(text: str) -> tuple[list[dict], str]:
    """Find the arm enumeration and split into arms.

    Anchors on an explicit 'arms:'/'groups:' cue (preferred) or a randomization
    ratio, so it does not misfire on incidental 'to' (e.g. 'moderate to severe').
    """
    # Preferred: "... one of N arms/groups: <A>, <B>, or <C>"
    m = re.search(r"\b(?:arms?|groups?|cohorts?)\b\s*:\s*(?P<list>[^.]+)", text, re.IGNORECASE)
    if not m:
        # Fallback: a randomization ratio followed by 'to <list>'
        m = re.search(r"\b\d+:\d+(?::\d+)*\b[^.]*?\bto\b(?P<list>[^.]+)", text, re.IGNORECASE)
    if not m:
        return [], ""
    span = m.group("list")
    span = re.sub(r"^\s*(one of\s+\w+\s+(?:arms?|groups?)\s*:?\s*)", "", span,
                  flags=re.IGNORECASE)
    # split on commas and 'or'/'and'
    parts = re.split(r",|\bor\b|\band\b", span)
    arms = []
    for p in parts:
        name = re.sub(r"\s+", " ", p).strip(" .:;")
        name = re.sub(r"^(the|a|an)\s+", "", name, flags=re.IGNORECASE).strip()
        # "to receive X" -> X ; "X orally twice daily for 5 days" -> X
        name = re.sub(r"^(?:to\s+)?(?:receive|receiving|be given|be treated with)\s+", "", name,
                      flags=re.IGNORECASE).strip()
        name = re.split(r"\s+(?:orally|intravenously|subcutaneously|once|twice|daily|"
                        r"for\s+\d+|at\s+a\s+dose|\()", name, maxsplit=1,
                        flags=re.IGNORECASE)[0].strip(" .:;")
        if arm_name_ok(name) and not name.lower().startswith(("approximately",)):
            arms.append({"name": name.title() if name.islower() else name,
                         "type": _arm_type(name)})
    # dedupe preserving order
    seen, out = set(), []
    for a in arms:
        if a["name"].lower() not in seen:
            seen.add(a["name"].lower())
            out.append(a)
    return out, m.group(0)[:200]


def extract_design(doc: Document, metadata_vals: dict, llm: LLM) -> tuple[
        list[FieldCandidate], DesignExtract]:
    text = doc.full_text
    de = DesignExtract()
    cands: list[FieldCandidate] = []

    # study type — interventional if intervention/randomization language present
    is_interventional = bool(re.search(
        r"\b(randomi[sz]ed|treatment|intervention|dose|administered)\b", text, re.IGNORECASE))
    de.study_type = "Interventional" if is_interventional else "Observational"
    cands.append(FieldCandidate("studyType", de.study_type, "design-heuristic",
                                de.study_type, 1))

    # intervention model
    mm = _MODEL_RE.search(text)
    if mm:
        de.intervention_model = _MODEL_NORM.get(mm.group(1).lower().replace("-", " "),
                                                mm.group(1).title())
        cands.append(FieldCandidate("interventionModel", de.intervention_model,
                                    "design-heuristic", mm.group(0), 1))

    # arms
    arms, src = _bulleted_arms(text)
    if not arms:
        arms, src = _parse_arms(text)
    de.arms, de.arms_source = arms, src
    if arms:
        # confidence: multiple arms cleanly parsed from an explicit ratio => higher
        ratio = bool(re.search(r"\b\d+:\d+(:\d+)+\b", text))
        de.arms_confidence = 0.8 if (ratio and len(arms) >= 2) else 0.55
        # A regex-parsed arm list never certifies itself: it is one candidate for the
        # ``armNames`` field, and only independent evidence can auto-accept it.
        de.arms_decision = "review"
        cands.append(FieldCandidate("armNames", "; ".join(a["name"] for a in arms),
                                    "design-heuristic", src, 1))
    return cands, de


def extract_llm_grounded(doc: Document, llm: LLM) -> list[GroundedCandidate]:
    """Two-pass, quote-grounded design-classification extraction (DESIGN.md L4/L5).

    Independent of the deterministic ``extract_design`` heuristics above — an
    LLM member's own read of the study-type/intervention-model language, each
    value grounded to a verbatim quote. See
    :mod:`usdm4_assure.llm.two_pass` for the shard mechanics.

    Args:
        doc: The ingested protocol document.
        llm: The model member. Returns ``[]`` if unavailable.
    """
    from usdm4_assure.extract.shards import SHARD_C2_DESIGN
    from usdm4_assure.llm.two_pass import extract_shard
    return extract_shard(doc, llm, SHARD_C2_DESIGN)
