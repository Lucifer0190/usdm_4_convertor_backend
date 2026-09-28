"""Rule -> repair map and the bounded repair loop (task 6.3, DESIGN.md L8).

A failed conformance rule is either something re-extraction can plausibly fix
(the rule concerns a value we extract: a primary endpoint, the planned age
range, the phase) or a **known gap** no re-extraction will fix (the assembler
emits no sponsor study role; timing windows and biomedical-concept coding are
not extracted yet). :data:`RULE_MAP` says which, per rule, and to which
``(domain, fields)`` it traces.

:func:`repair_loop` then runs at most :data:`MAX_ROUNDS` rounds. Each round
re-extracts only the domains the still-failing, re-extractable rules point at
(via an injected ``reextract``, escalating per round — see ``run_full``), adopts
a domain's re-extraction only if it improves a targeted field **and** loses no
value the domain already had, and re-validates only if something was adopted
(a round that changes nothing still lets the next, escalated round try). It
stops as soon as no re-extractable rule is failing. It always terminates.

Whatever is still failing afterwards is not silently dropped: each
re-extractable rule that exhausted its rounds is an ``ERROR`` finding and its
fields leave ``auto_accept`` for ``review``; each known gap is a ``WARNING``
naming the gap; an unmapped rule is a ``WARNING`` that no repair path exists.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from usdm4_assure.contracts import Decision, Finding, FindingKind, Severity
from usdm4_assure.extract.domains import DomainResult

MAX_ROUNDS = 2


@dataclass(frozen=True)
class RepairAction:
    domain: str
    fields: tuple[str, ...]
    reextract: bool          # False: a known gap re-extraction cannot fix
    note: str


def _re(domain: str, *fields: str, note: str) -> RepairAction:
    return RepairAction(domain, fields, True, note)


def _gap(domain: str, *fields: str, note: str) -> RepairAction:
    return RepairAction(domain, fields, False, note)


RULE_MAP: dict[str, RepairAction] = {
    # --- values we extract: re-extraction can fix ---------------------------------
    "DDF00005": _re("metadata", "protocolIdentifier", note="one sponsor study identifier"),
    "DDF00015": _re("metadata", "studyPhase", note="phase coded from the trial phase codelist"),
    "DDF00115": _re("metadata", "studyTitle", note="an official study title"),
    "DDF00041": _re("objectives", "primaryEndpoint", note="at least one primary endpoint"),
    "DDF00084": _re("objectives", "primaryObjective", note="exactly one primary objective"),
    "DDF00096": _re("objectives", "primaryObjective", "primaryEndpoint",
                    note="primary endpoints referenced by a primary objective"),
    "DDF00097": _re("eligibility", "plannedMinimumAge", "plannedMaximumAge",
                    note="a planned age range"),
    "DDF00098": _re("eligibility", "plannedSex", note="a planned sex"),
    "DDF00120": _re("design", "interventionModel", note="a coded intervention model"),
    "DDF00074": _re("design", "interventionModel",
                    note="intervention count consistent with the intervention model"),
    "DDF00172": _re("metadata", "protocolIdentifier", "sponsorName",
                    note="exactly one sponsor study identifier"),
    "DDF00201": _re("metadata", "sponsorName", note="exactly one sponsor study role"),
    # --- known gaps: re-extraction cannot fix -------------------------------------
    "DDF00140": _gap("metadata", "sponsorType",
                     note="the sponsor's organisation type is not extracted and is recorded "
                          "as CDISC 'Unknown', which the organisation-type codelist lacks "
                          "(task 6.4)"),
    "DDF00200": _gap("metadata", "sponsorType",
                     note="the sponsor's organisation type is not extracted and is recorded "
                          "as CDISC 'Unknown', which the organisation-type codelist lacks "
                          "(task 6.4)"),
    "DDF00006": _gap("soa", "timings", note="timing windows are not extracted (task 6.5)"),
    "DDF00025": _gap("soa", "timings", note="timing windows are not extracted (task 6.5)"),
    "DDF00031": _gap("soa", "timings", note="relative timing anchors are not extracted (task 6.5)"),
    "DDF00153": _gap("soa", "plannedDuration",
                     note="the main timeline's planned duration is not extracted (task 6.5)"),
    "DDF00075": _gap("soa", "activities",
                     note="activities are not coded to procedures or biomedical concepts"),
    "DDF00101": _gap("design", "interventions",
                     note="procedures referencing interventions are not extracted"),
    "DDF00087": _gap("soa", "ordering", note="linked-list ordering is emitted by the assembler"),
    "DDF00088": _gap("soa", "ordering", note="linked-list ordering is emitted by the assembler"),
}


@dataclass
class RepairOutcome:
    rounds: int = 0
    resolved: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    adopted: list[tuple[int, str]] = field(default_factory=list)   # (round, domain)
    findings: list[Finding] = field(default_factory=list)


def _finding(severity: Severity, domain: str, message: str, field_: str | None = None,
             rule: str | None = None) -> Finding:
    return Finding(FindingKind.REPAIR, severity, domain, message, field=field_,
                   expected=rule and "rule passes", found=rule)


def _targets(rules: set[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for rule in sorted(rules):
        action = RULE_MAP.get(rule)
        if action and action.reextract:
            out.setdefault(action.domain, set()).update(action.fields)
    return out


def _filled(result: DomainResult) -> int:
    return sum(v is not None for v in result.values().values())


def _improves(old: DomainResult, new: DomainResult, targets: set[str]) -> list[str]:
    """Targeted fields the re-extraction changes to a (new) value; [] if it regresses."""
    if _filled(new) < _filled(old):
        return []
    ov, nv = old.values(), new.values()
    return [f for f in sorted(targets) if nv.get(f) is not None and nv.get(f) != ov.get(f)]


def repair_loop(failed_rules: list[str], state: dict[str, DomainResult], *,
                reextract: Callable[[str, int], DomainResult | None],
                revalidate: Callable[[dict[str, DomainResult]], list[str]],
                max_rounds: int = MAX_ROUNDS) -> RepairOutcome:
    """Bounded validate -> re-extract -> re-validate loop. Mutates ``state`` in place.

    Args:
        failed_rules: Rule ids that failed the first validation.
        state: The current :class:`DomainResult` per extraction domain.
        reextract: ``(domain, round) -> DomainResult`` (``None`` to skip); should
            escalate with the round (wider evidence, then a stronger member).
        revalidate: Rebuilds and validates from ``state``; returns failed rule ids.
        max_rounds: Capped at :data:`MAX_ROUNDS`.
    """
    if max_rounds > MAX_ROUNDS:
        raise ValueError(f"the repair loop is bounded at {MAX_ROUNDS} rounds")
    outcome = RepairOutcome()
    initial = set(failed_rules)
    current = set(failed_rules)
    for rnd in range(1, max_rounds + 1):
        targets = _targets(current)
        if not targets:
            break
        outcome.rounds = rnd
        adopted_any = False
        for domain, fields_ in targets.items():
            if domain not in state:
                continue
            new = reextract(domain, rnd)
            changed = _improves(state[domain], new, fields_) if new is not None else []
            if not changed:
                continue
            before = state[domain].values()
            state[domain] = new
            adopted_any = True
            outcome.adopted.append((rnd, domain))
            for f in changed:
                outcome.findings.append(_finding(
                    Severity.INFO, domain, f"Round {rnd}: re-extracted {f} "
                    f"({before.get(f)!r} -> {new.values().get(f)!r}).", f))
        if not adopted_any:
            # Nothing changed, so nothing to re-validate — but the next round
            # escalates (a stronger member), so it still gets its chance.
            outcome.findings.append(_finding(Severity.INFO, "repair",
                                             f"Round {rnd} re-extracted no new values."))
            continue
        current = set(revalidate(state))
    outcome.resolved = sorted(initial - current)
    outcome.unresolved = sorted(current)
    for rule in outcome.resolved:
        action = RULE_MAP.get(rule)
        outcome.findings.append(_finding(Severity.INFO, action.domain if action else "repair",
                                         f"{rule} resolved by the repair loop.", rule=rule))
    _report_unresolved(outcome, state)
    return outcome


def _report_unresolved(outcome: RepairOutcome, state: dict[str, DomainResult]) -> None:
    for rule in outcome.unresolved:
        action = RULE_MAP.get(rule)
        if action is None:
            outcome.findings.append(_finding(Severity.WARNING, "repair",
                                             f"{rule} failed; no repair path is mapped for it.",
                                             rule=rule))
            continue
        if not action.reextract:
            outcome.findings.append(_finding(Severity.WARNING, action.domain,
                                             f"{rule} failed: known gap — {action.note}.",
                                             ",".join(action.fields), rule))
            continue
        outcome.findings.append(_finding(Severity.ERROR, action.domain,
                                         f"{rule} ({action.note}) still fails after "
                                         f"{outcome.rounds} repair round(s).",
                                         ",".join(action.fields), rule))
        result = state.get(action.domain)
        for f in result.fields if result else []:
            if f.field in action.fields and f.decision is Decision.AUTO_ACCEPT:
                f.decision = Decision.REVIEW
