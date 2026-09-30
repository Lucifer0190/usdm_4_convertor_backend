"""The CORE gate's summary: CORE's result object differs from the d4k one."""
from __future__ import annotations

from usdm4.core.core_validation_result import CoreRuleFinding, CoreValidationResult

from usdm4_assure.validate.gate import _summarize_core


def test_a_core_result_is_summarised_with_its_failing_rules():
    result = CoreValidationResult(
        findings=[CoreRuleFinding("DDF00125", "desc", "msg", [{"path": "a"}, {"path": "b"}]),
                  CoreRuleFinding("DDF00201", "desc", "msg", [{"path": "c"}])],
        execution_errors=[{"rule": "x"}], rules_executed=200, rules_skipped=7,
        ct_packages_loaded=["sdtm-2025-09-26"])
    s = _summarize_core(result)
    assert s["passed"] is False and s["failed_rules"] == ["DDF00125", "DDF00201"]
    assert s["findings"] == 3 and s["rules_run"] == 200 and s["rules_skipped"] == 7
    assert s["execution_errors"] == 1 and s["ct_packages_loaded"] == 1


def test_a_clean_core_result_passes():
    s = _summarize_core(CoreValidationResult(rules_executed=200))
    assert s["passed"] is True and s["failed_rules"] == [] and s["findings"] == 0
