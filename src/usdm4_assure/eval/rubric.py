"""The multi-study accuracy rubric — what "N% accurate" means for this project.

A claim like "89% accurate" is only meaningful against a fixed definition, so this
module is that definition, applied identically to every study and every run.

**Items.** One item is one element of a hand-corrected reference USDM:

* ``scalars``      title, sponsor, phase, protocol id, version, study type, intervention model
* ``identifiers``  each registry / regulatory / compound identifier
* ``arms``, ``interventions``
* ``criteria``     each inclusion / exclusion criterion
* ``objectives``, ``endpoints``, ``estimands``
* ``epochs``, ``encounters`` (visits), ``activities``
* ``marks``        each scheduled (visit, activity) pair of the Schedule of Activities
* ``vendors``      organisations other than the sponsor, registries and regulators

An item is **matched** when the delivered study holds an equivalent element
(one-to-one, best match first). Thresholds are token-overlap (Jaccard) because the
reference condenses wording that the protocol states verbatim.

**Accuracy** = matched / (reference items + spurious delivered items). A wrong or
invented element costs as much as an omission, so a system cannot raise its score by
delivering more. **Recall** = matched / reference items is reported beside it.

A category the reference does not contain is not scored (nothing to check it against).
The reference is hand-corrected but not perfect: results are a lower bound wherever
the reference itself is incomplete.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_STOP = frozenset({"the", "and", "for", "with", "that", "this", "are", "was", "were", "will",
                   "from", "has", "have", "not", "any", "all", "who", "their", "than"})
_REGULATORY_ORGS = {"study registry", "regulatory agency"}
_SPONSOR_ORGS = {"drug company", "pharmaceutical company", "sponsor"}


# --- text helpers ------------------------------------------------------------------- #
def _norm(text: str | None) -> str:
    t = (text or "").replace("â€‘", "-").replace("‑", "-").replace("−", "-").lower()
    t = re.sub(r"(?<![a-z0-9])-(?=\d)", " neg", t)       # "Day -1" must differ from "Day 1"
    return re.sub(r"[^a-z0-9 ]+", " ", t)


def _tokens(text: str | None) -> set[str]:
    """Content words (3+ letters) plus every token holding a digit.

    Numbers are what tell visits apart ("Day 1" / "Day 15", "Visit 1" / "Visit 10"), so they
    are never dropped as short words.
    """
    return {w for w in _norm(text).split()
            if (len(w) > 2 or any(ch.isdigit() for ch in w)) and w not in _STOP}


def _jaccard(a: str | None, b: str | None) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def _display(item: dict) -> str:
    """The human-readable name of an epoch / visit / activity.

    The assembler keeps a machine name ("T1-ENCOUNTER-3") and puts the protocol's own
    text in ``label``; hand-built references usually have only ``name``.
    """
    return item.get("label") or item.get("name") or ""


def _decode(x) -> str:
    return ((x or {}).get("decode") or "") if isinstance(x, dict) else str(x or "")


# --- view of a USDM study ------------------------------------------------------------ #
def view_of(wrapper: dict) -> dict:
    """The comparable content of one USDM study (wrapper or bare study)."""
    study = wrapper.get("study", wrapper)
    version = (study.get("versions") or [{}])[0]
    design = (version.get("studyDesigns") or [{}])[0]

    ids = [i.get("text") for i in version.get("studyIdentifiers", []) if i.get("text")]
    protocol_id = next((i for i in ids if re.fullmatch(r"[A-Za-z]\d{7}", i)), None)
    titles = version.get("titles", [])
    official = next((t["text"] for t in titles if "official" in _decode(t.get("type")).lower()),
                    study.get("name"))
    orgs = list(study.get("organizations", [])) + list(version.get("organizations", []))
    org_by_id = {o.get("id"): o for o in orgs}
    sponsor = None
    for i in version.get("studyIdentifiers", []):
        if i.get("text") == protocol_id and i.get("scopeId") in org_by_id:
            sponsor = org_by_id[i["scopeId"]].get("name")
    if sponsor is None:
        sponsor = next((o.get("name") for o in orgs
                        if _decode(o.get("type")).lower() in _SPONSOR_ORGS), None)

    phase = design.get("studyPhase") or version.get("studyPhase") or {}
    phase_text = _decode(phase) or _decode((phase or {}).get("standardCode"))
    scalars = {
        "title": official, "sponsor": sponsor, "phase": phase_text or None,
        "protocol_id": protocol_id, "version": version.get("versionIdentifier"),
        "study_type": _decode(design.get("studyType")) or None,
        "model": _decode(design.get("model")) or _decode(design.get("interventionModel")) or None,
    }

    enc = {e["id"]: _display(e) for e in design.get("encounters", []) if "id" in e}
    act = {a["id"]: _display(a) for a in design.get("activities", []) if "id" in a}
    marks = []
    for timeline in design.get("scheduleTimelines", []):
        for inst in timeline.get("instances", []):
            e = enc.get(inst.get("encounterId"))
            for aid in inst.get("activityIds", []) or []:
                if e and act.get(aid):
                    marks.append((e, act[aid]))

    criteria = []
    items = {i.get("id"): i for i in version.get("eligibilityCriterionItems", [])}
    for c in design.get("eligibilityCriteria", []):
        text = c.get("text") or items.get(c.get("criterionItemId"), {}).get("text") or c.get("name")
        if text:
            criteria.append(text)

    objectives, endpoints = [], []
    for o in design.get("objectives", []):
        if o.get("text"):
            objectives.append(o["text"])
        endpoints += [e["text"] for e in o.get("endpoints", []) if e.get("text")]

    def estimand_text(e: dict) -> str:
        keys = ("name", "text", "description", "label", "variableOfInterest", "populationSummary",
                "summaryMeasure", "analysisPopulation", "treatment")
        out: list[str] = []

        def walk(v):
            if isinstance(v, str) and len(v) > 3:
                out.append(v)
            elif isinstance(v, dict):
                for k, x in v.items():
                    if k in keys or isinstance(x, (dict, list)):
                        walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
        walk({k: v for k, v in e.items() if k in keys or isinstance(v, (dict, list))})
        return " ".join(out)

    vendors = [o.get("name") for o in orgs
               if o.get("name") and _decode(o.get("type")).lower() not in _REGULATORY_ORGS | _SPONSOR_ORGS]
    return {
        "scalars": {k: v for k, v in scalars.items() if v},
        "identifiers": ids, "arms": [a.get("name") for a in design.get("arms", []) if a.get("name")],
        "interventions": [i.get("name") for i in (version.get("studyInterventions")
                                                  or design.get("studyInterventions") or []) if i.get("name")],
        "criteria": criteria, "objectives": objectives, "endpoints": endpoints,
        "estimands": [estimand_text(e) for e in design.get("estimands", [])],
        "epochs": [_display(e) for e in design.get("epochs", []) if _display(e)],
        "encounters": [_display(e) for e in design.get("encounters", []) if _display(e)],
        "activities": [_display(a) for a in design.get("activities", []) if _display(a)],
        "marks": marks, "vendors": vendors,
    }


# --- matching ------------------------------------------------------------------------- #
def _scalar_equal(key: str, got: str, ref: str) -> bool:
    if key == "title":
        return _jaccard(got, ref) >= 0.8
    if key == "sponsor":
        return _jaccard(got, ref) >= 0.5 or _norm(ref).strip() in _norm(got)
    if key == "protocol_id":
        return got.strip().lower() == ref.strip().lower()
    if key == "phase":
        g, r = re.findall(r"[1-4]", got), re.findall(r"[1-4]", ref)
        roman = {"iii": "3", "ii": "2", "iv": "4", "i": "1"}
        g = g or [roman[w] for w in re.findall(r"\b(iii|ii|iv|i)\b", got.lower())]
        r = r or [roman[w] for w in re.findall(r"\b(iii|ii|iv|i)\b", ref.lower())]
        return bool(g) and g == r
    if key == "version":
        g, r = re.findall(r"\d+", got), re.findall(r"\d+", ref)
        return bool(g and r) and int(g[0]) == int(r[0])
    if key in ("study_type", "model"):
        gw, rw = set(_norm(got).split()), set(_norm(ref).split())
        return bool(gw & rw - {"study", "trial"})
    return _norm(got) == _norm(ref)


def _greedy(reference: list, delivered: list, similar, threshold: float) -> int:
    used: set[int] = set()
    matched = 0
    for r in reference:
        best, best_i = 0.0, None
        for i, d in enumerate(delivered):
            if i in used:
                continue
            s = similar(r, d)
            if s > best:
                best, best_i = s, i
        if best_i is not None and best >= threshold:
            used.add(best_i)
            matched += 1
    return matched


@dataclass
class Category:
    matched: int = 0
    reference: int = 0
    delivered: int = 0

    @property
    def spurious(self) -> int:
        return max(0, self.delivered - self.matched)

    @property
    def recall(self) -> float:
        return self.matched / self.reference if self.reference else 1.0


_THRESHOLDS = {"arms": 0.3, "interventions": 0.3, "epochs": 0.5, "encounters": 0.5,
               "activities": 0.6, "criteria": 0.5, "objectives": 0.4, "endpoints": 0.5,
               "estimands": 0.3, "vendors": 0.5}


@dataclass
class StudyScore:
    categories: dict[str, Category] = field(default_factory=dict)

    @property
    def matched(self) -> int:
        return sum(c.matched for c in self.categories.values())

    @property
    def reference(self) -> int:
        return sum(c.reference for c in self.categories.values())

    @property
    def spurious(self) -> int:
        return sum(c.spurious for c in self.categories.values())

    @property
    def accuracy(self) -> float:
        denom = self.reference + self.spurious
        return self.matched / denom if denom else 1.0

    @property
    def recall(self) -> float:
        return self.matched / self.reference if self.reference else 1.0


def score_study(delivered: dict, reference: dict) -> StudyScore:
    """Score one delivered USDM against one reference USDM (wrappers or bare studies)."""
    got, ref = view_of(delivered), view_of(reference)
    out = StudyScore()

    sc = Category()
    for key, ref_value in ref["scalars"].items():
        sc.reference += 1
        value = got["scalars"].get(key)
        if value:
            sc.delivered += 1
            if _scalar_equal(key, str(value), str(ref_value)):
                sc.matched += 1
    if sc.reference:
        out.categories["scalars"] = sc

    def add(name: str, similar, threshold: float) -> None:
        if not ref[name]:
            return
        out.categories[name] = Category(
            matched=_greedy(ref[name], got[name], similar, threshold),
            reference=len(ref[name]), delivered=len(got[name]))

    add("identifiers", lambda a, b: 1.0 if _norm(a).strip() == _norm(b).strip() else 0.0, 1.0)
    for name, th in _THRESHOLDS.items():
        add(name, _jaccard, th)
    add("marks", lambda a, b: min(_jaccard(a[0], b[0]), _jaccard(a[1], b[1])), 0.6)
    return out
