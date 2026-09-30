"""Integrity F — the conformance gates (DESIGN.md §3.F).

Gate 1: pydantic structural validity (Wrapper.model_validate).
Gate 2: d4k rule library      — offline, no key.
Gate 3: CDISC CORE            — official; needs CDISC_LIBRARY_API_KEY.

Returns a plain dict so the pipeline/CLI stay decoupled from usdm4 internals.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def _get(obj, name):
    """Read an attr that may be a plain value, a property, or a zero-arg method."""
    if not hasattr(obj, name):
        return None
    v = getattr(obj, name)
    try:
        return v() if callable(v) else v
    except Exception:  # noqa: BLE001
        return None


def _summarize(result) -> dict:
    passed = _get(result, "passed")
    rules = _get(result, "count")
    findings = _get(result, "finding_count")
    failed_rules = []
    outcomes = getattr(result, "outcomes", None)
    if isinstance(outcomes, dict):
        failed_rules = [
            k for k, o in outcomes.items()
            if getattr(getattr(o, "status", None), "name", "") == "FAILURE"
        ]
    return {"passed": passed, "rules_run": rules, "findings": findings,
            "failed_rules": failed_rules}


def _summarize_core(result) -> dict:
    """CORE's result object is not the d4k one (no ``passed``/``outcomes``): it carries
    ``findings`` (one per failing rule, each with its instances), ``execution_errors``
    (rules that could not run on this file) and the controlled-terminology packages it
    actually loaded. Summarised in the same shape as :func:`_summarize` plus those."""
    findings = getattr(result, "findings", []) or []
    return {"passed": bool(getattr(result, "is_valid", False)),
            "rules_run": getattr(result, "rules_executed", None),
            "findings": getattr(result, "finding_count", None),
            "failed_rules": [f.rule_id for f in findings],
            "rules_skipped": getattr(result, "rules_skipped", None),
            "execution_errors": getattr(result, "execution_error_count", None),
            "ct_packages_loaded": len(getattr(result, "ct_packages_loaded", []) or [])}


def validate_wrapper(wrapper: dict, *, run_core: bool = False) -> dict:
    """Validate an in-memory USDM wrapper dict through all available gates.

    Runs the structural (pydantic) gate first; if it fails, the rule gates are
    skipped because they need a well-formed tree. The d4k rule gate runs offline;
    the CORE gate is optional and needs a CDISC Library API key.

    Args:
        wrapper: A USDM 4.0 wrapper as a plain dict (``{"study": ...,
            "usdmVersion": ...}``).
        run_core: If ``True``, run the CDISC CORE gate. Skipped with a note when
            ``CDISC_LIBRARY_API_KEY`` is not set in the environment.

    Returns:
        A report dict ``{"structural": ..., "d4k": ..., "core": ...}`` where each
        entry is either a summary (``passed``, ``rules_run``, ``findings``,
        ``failed_rules``), a ``{"skipped": reason}``, or an ``{"error": msg}``.
    """
    report: dict = {"structural": None, "d4k": None, "core": None}

    # Gate 1 — pydantic structural
    try:
        from usdm4.api.wrapper import Wrapper
        Wrapper.model_validate(wrapper)
        report["structural"] = {"passed": True}
    except Exception as e:  # noqa: BLE001
        report["structural"] = {"passed": False, "error": str(e)[:300]}
        return report  # structural failure -> stop; downstream needs a valid tree

    # usdm4 facade validates a file path; write to a temp file.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "study.usdm.json"
        # model_dump leaves UUID/enum objects; default=str makes them serializable.
        p.write_text(json.dumps(wrapper, default=str), encoding="utf-8")

        from usdm4 import USDM4
        # Gate 2 — d4k rules (offline)
        try:
            report["d4k"] = _summarize(USDM4().validate(str(p)))
        except Exception as e:  # noqa: BLE001
            report["d4k"] = {"error": str(e)[:300]}

        # Gate 3 — CDISC CORE (optional; needs key)
        if run_core:
            if not os.environ.get("CDISC_LIBRARY_API_KEY"):
                report["core"] = {"skipped": "CDISC_LIBRARY_API_KEY not set"}
            else:
                try:
                    report["core"] = _summarize_core(USDM4().validate_core(str(p)))
                except Exception as e:  # noqa: BLE001
                    report["core"] = {"error": str(e)[:300]}
        else:
            report["core"] = {"skipped": "run_core=False"}

    return report
