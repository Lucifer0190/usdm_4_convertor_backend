"""Per-section assembler fallback and the assembler reliance ratio (task 6.3, DESIGN.md L7).

The usdm4 ``Assembler`` is all-or-nothing: one bad section — a timeline it
cannot build, an estimand reference it rejects at schema validation — and no
study comes back at all. This module salvages the rest, one step at a time,
reporting every step:

1. **Sub-section degrade.** If the objectives section fails because of its
   estimands, retry with the estimands removed (objectives and endpoints
   survive).
2. **Section drop.** Otherwise drop the optional section the assembler's
   errors point at (``soa``, ``objectives``, ``amendments``) and retry. If the
   errors don't name one, drop in a fixed order, least-core first, and say so.
   Required sections (identification, document, population, design, study)
   have no fallback — a failure there is reported as a failed assembly.
3. **Builder fallback.** A dropped objectives section is rebuilt directly with
   the assembler's own ``Builder`` and ``Encoder`` (same ID sequence, same
   level coding as ``ObjectivesAssembler``), without estimands.

The sub-assemblers also swallow their own exceptions, so "the assembler
returned a study" does not mean every supplied section is in it: each
optional section is checked for presence in the result and counted as dropped
if missing. The **assembler reliance ratio** — sections the assembler itself
produced / sections supplied — is reported with every assembly (PLAN.md §8,
DESIGN.md L7); builder-fallback sections do not count toward it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from usdm4_assure.contracts import Finding, FindingKind, Severity

REQUIRED = ("identification", "document", "population", "study_design", "study")
OPTIONAL = ("soa", "objectives", "amendments")
BLIND_DROP_ORDER = ("amendments", "soa", "objectives")
_MARKERS = {
    "soa": ("timeline_assembler", "schema validation: soa"),
    "objectives": ("objectives_assembler", "schema validation: objectives", "estimand"),
    "amendments": ("amendments_assembler", "schema validation: amendments"),
}
_DOMAIN = {"soa": "soa", "objectives": "objectives", "amendments": "amendments"}


@dataclass
class AssemblyOutcome:
    study_ok: bool
    wrapper: dict | None
    errors: list[str]
    supplied: list[str]
    assembler_sections: list[str] = field(default_factory=list)
    fallback_sections: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    attempts: int = 0

    @property
    def reliance_ratio(self) -> float | None:
        """Sections the usdm4 assembler produced / sections supplied."""
        return len(self.assembler_sections) / len(self.supplied) if self.supplied else None

    def report(self) -> dict:
        return {"supplied": self.supplied, "assembler": self.assembler_sections,
                "fallback": self.fallback_sections, "dropped": self.dropped,
                "attempts": self.attempts, "reliance_ratio": self.reliance_ratio}


def _finding(severity: Severity, section: str, message: str) -> Finding:
    return Finding(FindingKind.SANITIZER, severity, _DOMAIN.get(section, "assembly"), message,
                   field=section)


def _messages(errors) -> list[str]:
    """Error-level entries as ``"<message> [<class>.<method>]"``.

    ``simple_error_log.Errors`` exposes its entries via ``to_dict()`` (there is
    no ``.errors`` attribute — reading one silently yielded nothing before
    this module). The location names the sub-assembler that failed, which is
    what attributes a failure to a section.
    """
    out = []
    for item in errors.to_dict():
        loc = item.get("location") or {}
        where = ".".join(v for v in (loc.get("class_name"), loc.get("method_name")) if v)
        first_line = str(item.get("message", "")).strip().split("\n\n")[0]
        out.append(f"{first_line} [{where}]" if where else first_line)
    return out


def _culprit(messages: list[str], candidates: list[str]) -> tuple[str | None, str]:
    """The optional section the assembler's errors name, and the message naming it."""
    for section in candidates:
        for msg in messages:
            if any(marker in msg.lower() for marker in _MARKERS[section]):
                return section, msg
    return None, ""


def _first_design(asm):
    versions = getattr(asm.study, "versions", None) or []
    designs = versions[0].studyDesigns if versions else []
    return versions[0] if versions else None, designs[0] if designs else None


def _unmaterialised(asm, data: dict) -> list[str]:
    """Supplied optional sections that are absent from the assembled study."""
    version, design = _first_design(asm)
    present = {
        "soa": bool(design is not None and design.scheduleTimelines),
        "objectives": bool(design is not None and design.objectives)
                      or not (data.get("objectives") or {}).get("objectives"),
        "amendments": bool(version is not None and version.amendments),
    }
    return [s for s in OPTIONAL if data.get(s) and not present[s]]


def _objectives_fallback(asm, block: dict) -> tuple[int, list[str]]:
    """Rebuild objectives + endpoints with the assembler's own builder.

    Returns ``(built, failures)`` — every objective the builder could not
    create is named in ``failures``, never skipped silently.
    """
    from usdm4.api.endpoint import Endpoint
    from usdm4.api.objective import Objective
    from usdm4.assembler.encoder import Encoder

    builder = getattr(asm, "_builder", None)   # usdm4==0.29.0 (PINS.md) keeps it here
    _, design = _first_design(asm)
    if builder is None or design is None:
        return 0, ["no builder or study design to attach objectives to"]
    encoder = Encoder(builder, asm._errors)
    built, failures = [], []
    for i, item in enumerate(block.get("objectives", []), start=1):
        try:
            endpoints = [builder.create(Endpoint, {
                "name": e.get("name") or f"ENDPOINT-{i}-{j}", "label": "", "description": "",
                "text": e["text"], "purpose": "",
                "level": encoder.endpoint_level(e.get("level", ""))})
                for j, e in enumerate(item.get("endpoints", []), start=1)]
            objective = builder.create(Objective, {
                "name": item.get("name") or f"OBJECTIVE-{i}", "label": "", "description": "",
                "text": item["text"], "level": encoder.objective_level(item.get("level", "")),
                "endpoints": [e for e in endpoints if e is not None]})
        except Exception as exc:  # noqa: BLE001 — one bad objective must not sink the others
            failures.append(f"objective {i}: {type(exc).__name__}: {exc}")
            continue
        if objective is None:
            failures.append(f"objective {i}: the builder returned nothing")
        else:
            built.append(objective)
    design.objectives = built
    return len(built), failures


def assemble(data: dict, *, name: str = "USDM4-Assure", version: str = "0.1.0",
             sites: dict[str, str | None] | None = None) -> AssemblyOutcome:
    """Run the usdm4 assembler with per-section fallback.

    Args:
        data: The (sanitized) ``AssemblerInput``-shaped dict.
        name / version: Passed through to ``Assembler.wrapper()``.
        sites: Extracted organization names (task 6.4,
            ``extract.sites.FIELDS``), attached directly via
            :func:`usdm4_assure.assemble.sites.attach_organizations` since
            the assembler's own input schema cannot represent them.
    """
    import usdm4
    from simple_error_log.errors import Errors
    from usdm4.assembler.assembler import Assembler

    root = os.path.dirname(usdm4.__file__)
    supplied = list(REQUIRED) + [s for s in OPTIONAL if data.get(s)]
    outcome = AssemblyOutcome(study_ok=False, wrapper=None, errors=[], supplied=supplied)
    attempt = dict(data)
    for _ in range(len(OPTIONAL) + 2):         # bounded: one retry per degrade step
        outcome.attempts += 1
        errors = Errors()
        asm = Assembler(root, errors)
        asm.execute(attempt)
        outcome.errors = _messages(errors)
        if asm.study is not None:
            break
        remaining = [s for s in OPTIONAL if attempt.get(s)]
        section, msg = _culprit(outcome.errors, remaining)
        if section == "objectives" and attempt["objectives"].get("estimands"):
            attempt["objectives"] = {**attempt["objectives"], "estimands": []}
            outcome.findings.append(_finding(Severity.ERROR, "estimands",
                                             f"The assembler rejected the estimands ({msg[:160]}); "
                                             "retried with objectives but no estimands."))
            continue
        if section is None:
            section = next((s for s in BLIND_DROP_ORDER if s in remaining), None)
            if section is None:
                outcome.findings.append(_finding(
                    Severity.ERROR, "assembly", "Assembly failed in a required section; there "
                    f"is no fallback for it. First error: {outcome.errors[:1]}"))
                return outcome
            msg = "the assembler's errors do not name a section; dropping it to isolate the failure"
        attempt[section] = None
        outcome.dropped.append(section)
        outcome.findings.append(_finding(Severity.ERROR, section,
                                         f"The assembler rejected the {section} section "
                                         f"({msg[:160]}); retried without it."))
    else:
        outcome.findings.append(_finding(Severity.ERROR, "assembly",
                                         "Assembly failed after every fallback step."))
        return outcome

    for section in _unmaterialised(asm, attempt):
        outcome.dropped.append(section)
        outcome.findings.append(_finding(Severity.ERROR, section,
                                         f"The {section} section was supplied but is missing from "
                                         "the assembled study (the sub-assembler failed quietly)."))
    if "objectives" in outcome.dropped and (data.get("objectives") or {}).get("objectives"):
        n, failures = _objectives_fallback(asm, data["objectives"])
        if n:
            outcome.fallback_sections.append("objectives")
            outcome.findings.append(_finding(Severity.WARNING, "objectives",
                                             f"{n} objective(s) rebuilt by the per-section builder "
                                             "fallback; estimands are not included."))
        for failure in failures:
            outcome.findings.append(_finding(Severity.ERROR, "objectives",
                                             f"Builder fallback could not rebuild {failure}."))
    if "soa" not in outcome.dropped:
        from usdm4_assure.assemble.soa import repair_timeline
        _, design = _first_design(asm)
        if design is not None:
            for note in repair_timeline(asm._builder, design.scheduleTimelines,
                                        design.encounters, design.epochs):
                outcome.findings.append(_finding(Severity.INFO, "soa", note))
    if sites:
        from usdm4_assure.assemble.sites import attach_organizations
        outcome.findings += attach_organizations(asm, sites)
    outcome.assembler_sections = [s for s in supplied if s not in outcome.dropped]
    outcome.study_ok = True
    outcome.wrapper = asm.wrapper(name=name, version=version).model_dump(by_alias=True)
    return outcome
