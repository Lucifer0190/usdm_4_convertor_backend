"""Bounded repair loop (task 6.3): rule map, adoption guard, termination, reporting.

Fake reextract/revalidate closures pin the loop's logic exactly; the real
assembler is exercised by test_full.py / test_sanitize.py.
"""
from __future__ import annotations

import pytest

from usdm4_assure.contracts import AssuredField, Decision, FindingKind, Severity
from usdm4_assure.extract.domains import DomainResult
from usdm4_assure.validate.repair import MAX_ROUNDS, RULE_MAP, repair_loop


def _f(name: str, value: str | None, decision: Decision = Decision.REVIEW,
       domain: str = "eligibility") -> AssuredField:
    return AssuredField(name, value, [], value is not None, 1, "supported", 0.9, decision,
                        domain=domain)


def _elig(min_age=None, max_age=None, sex="ALL", decision=Decision.REVIEW) -> DomainResult:
    return DomainResult([_f("plannedMinimumAge", min_age, decision),
                         _f("plannedMaximumAge", max_age, decision),
                         _f("plannedSex", sex, decision)])


class _Recorder:
    """reextract/revalidate fakes that record their calls."""

    def __init__(self, results: dict[int, DomainResult | None], failing_after: list[list[str]]):
        self.results, self.failing_after = results, list(failing_after)
        self.reextract_calls: list[tuple[str, int]] = []
        self.revalidations = 0

    def reextract(self, domain: str, rnd: int):
        self.reextract_calls.append((domain, rnd))
        return self.results.get(rnd)

    def revalidate(self, _state) -> list[str]:
        self.revalidations += 1
        return self.failing_after.pop(0) if self.failing_after else []


def test_rule_map_actions_are_consistent():
    for rule, action in RULE_MAP.items():
        assert rule.startswith("DDF") and action.fields and action.note
        assert action.domain in {"metadata", "design", "eligibility", "objectives", "soa"}


def test_known_gaps_spend_no_rounds_and_are_explained():
    rec = _Recorder({}, [])
    out = repair_loop(["DDF00140", "DDF00153"], {"eligibility": _elig()},
                      reextract=rec.reextract, revalidate=rec.revalidate)
    assert out.rounds == 0 and rec.reextract_calls == [] and rec.revalidations == 0
    assert out.unresolved == ["DDF00140", "DDF00153"]
    assert all(f.severity is Severity.WARNING and "known gap" in f.message
               for f in out.findings)


def test_rule_resolved_in_round_one():
    state = {"eligibility": _elig()}
    rec = _Recorder({1: _elig("18", "75")}, [[]])
    out = repair_loop(["DDF00097"], state, reextract=rec.reextract, revalidate=rec.revalidate)
    assert out.rounds == 1 and out.resolved == ["DDF00097"] and out.unresolved == []
    assert out.adopted == [(1, "eligibility")]
    assert state["eligibility"].values()["plannedMinimumAge"] == "18"
    assert any(f.kind is FindingKind.REPAIR and "plannedMinimumAge" in f.message
               for f in out.findings)


def test_no_progress_in_round_one_still_lets_escalated_round_two_try():
    state = {"eligibility": _elig()}
    rec = _Recorder({1: _elig(), 2: _elig("18", "65")}, [[]])
    out = repair_loop(["DDF00097"], state, reextract=rec.reextract, revalidate=rec.revalidate)
    assert rec.reextract_calls == [("eligibility", 1), ("eligibility", 2)]
    assert rec.revalidations == 1            # round 1 changed nothing: no revalidation
    assert out.resolved == ["DDF00097"] and out.adopted == [(2, "eligibility")]


def test_unresolvable_rule_stops_at_the_bound_and_demotes_its_fields():
    state = {"eligibility": _elig(sex="ALL", decision=Decision.AUTO_ACCEPT)}
    # Every round "improves" the value but validation never passes.
    rec = _Recorder({1: _elig(sex="MALE"), 2: _elig(sex="FEMALE")}, [["DDF00098"], ["DDF00098"]])
    out = repair_loop(["DDF00098"], state, reextract=rec.reextract, revalidate=rec.revalidate)
    assert out.rounds == MAX_ROUNDS == 2 and len(rec.reextract_calls) == 2
    assert out.unresolved == ["DDF00098"]
    err = next(f for f in out.findings if f.severity is Severity.ERROR)
    assert "still fails after 2 repair round(s)" in err.message and err.found == "DDF00098"
    sex = next(f for f in state["eligibility"].fields if f.field == "plannedSex")
    assert sex.decision is Decision.REVIEW   # left auto_accept -> review


def test_regressing_reextraction_is_not_adopted():
    state = {"eligibility": _elig("18", "75", sex="ALL")}
    worse = DomainResult([_f("plannedMinimumAge", None), _f("plannedMaximumAge", None),
                          _f("plannedSex", "MALE")])    # new sex, but loses both ages
    rec = _Recorder({1: worse, 2: worse}, [])
    out = repair_loop(["DDF00098"], state, reextract=rec.reextract, revalidate=rec.revalidate)
    assert out.adopted == [] and rec.revalidations == 0
    assert state["eligibility"].values()["plannedMinimumAge"] == "18"


def test_unmapped_rule_is_reported_not_dropped():
    rec = _Recorder({}, [])
    out = repair_loop(["DDF99999"], {}, reextract=rec.reextract, revalidate=rec.revalidate)
    assert out.unresolved == ["DDF99999"]
    assert "no repair path" in out.findings[0].message


def test_domain_missing_from_state_is_skipped():
    rec = _Recorder({1: _elig("18", "75")}, [])
    out = repair_loop(["DDF00097"], {}, reextract=rec.reextract, revalidate=rec.revalidate)
    assert rec.reextract_calls == [] and out.unresolved == ["DDF00097"]


def test_the_bound_cannot_be_raised():
    with pytest.raises(ValueError, match="bounded"):
        repair_loop([], {}, reextract=lambda d, r: None, revalidate=lambda s: [],
                    max_rounds=3)
