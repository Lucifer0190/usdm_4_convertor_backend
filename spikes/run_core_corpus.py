#!/usr/bin/env python3
"""Phase 7 spike — full corpus run; publishes ``docs/scoreboard.md`` (task 7.1).

Runs ``run_full()`` over every usdm_data protocol PDF (:mod:`usdm4_assure.eval.corpus`),
under the pinned ``usdm4`` / d4k rule set / errata revision recorded in ``PINS.md``, and
reports what PLAN.md §8 asks every full run to report: auto-accept coverage, review
burden, the assembler reliance ratio, and (from task 4.1's four held-out, frozen-label
studies only — the rest of the corpus has no ground truth) realized error.

**CORE is opt-in and honestly reported when skipped.** Pass ``--core`` to also run the
CDISC CORE gate; it needs ``CDISC_LIBRARY_API_KEY`` in the environment (a free key from
the CDISC Library). Without either, every study's CORE result is ``skipped`` — exactly
what ``validate/gate.py`` already reports per study — never a fabricated pass rate for a
gate that did not run.

Usage::

    .venv/Scripts/python.exe spikes/run_core_corpus.py [--core] [--limit N]

Writes ``spikes/reports/core_corpus.json`` and ``docs/scoreboard.md``.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from usdm4_assure.eval.corpus import CORPUS_ROOT, studies
from usdm4_assure.eval.report import run_eval
from usdm4_assure.pipeline import run_full

REPORT_PATH = REPO_ROOT / "spikes" / "reports" / "core_corpus.json"
SCOREBOARD_PATH = REPO_ROOT / "docs" / "scoreboard.md"
OUT_DIR = REPO_ROOT / "data" / "out_core"


@dataclass
class StudyRun:
    study_id: str
    ok: bool
    error: str | None = None
    n_fields: int = 0
    n_auto_accept: int = 0
    n_review: int = 0
    n_block: int = 0
    structural_passed: bool | None = None
    d4k_passed: bool | None = None
    d4k_failed_rules: list[str] = field(default_factory=list)
    core_status: str = "not_run"      # passed | failed | skipped | error
    reliance_ratio: float | None = None
    repair_resolved: list[str] = field(default_factory=list)
    repair_unresolved: list[str] = field(default_factory=list)


def _core_status(core: dict) -> str:
    if "skipped" in core:
        return "skipped"
    if "error" in core:
        return "error"
    return "passed" if core.get("passed") else "failed"


def run_one(study, run_core: bool) -> StudyRun:
    """One study's ``run_full()``, tallied. A broken study never sinks the corpus run."""
    try:
        result = run_full(study.pdf_path, out_dir=OUT_DIR / study.study_id, run_core=run_core)
    except Exception as exc:  # noqa: BLE001
        return StudyRun(study.study_id, ok=False, error=f"{type(exc).__name__}: {exc}")

    estimand_fields = result.estimands.assured_fields() if result.estimands else []
    all_assured = (result.assured_meta + result.assured_design + result.assured_eligibility
                  + result.assured_objectives + estimand_fields + result.assured_sites)
    tally = Counter(a.decision.value for a in all_assured)
    validation = result.study.get("validation") or {}
    d4k = validation.get("d4k") or {}
    return StudyRun(
        study.study_id, ok=bool(result.study.get("ok")), n_fields=len(all_assured),
        n_auto_accept=tally["auto_accept"], n_review=tally["review"], n_block=tally["block"],
        structural_passed=(validation.get("structural") or {}).get("passed"),
        d4k_passed=d4k.get("passed"), d4k_failed_rules=d4k.get("failed_rules") or [],
        core_status=_core_status(validation.get("core") or {}),
        reliance_ratio=(result.study.get("assembly") or {}).get("reliance_ratio"),
        repair_resolved=result.repair.resolved, repair_unresolved=result.repair.unresolved)


def _rate(items: list, predicate) -> str:
    known = [x for x in items if predicate(x) is not None]
    if not known:
        return "n/a"
    return f"{sum(bool(predicate(x)) for x in known)}/{len(known)}"


def summarize(runs: list[StudyRun], labelled) -> dict:
    ok = [r for r in runs if r.ok]
    total_fields = sum(r.n_fields for r in ok)
    reliance = [r.reliance_ratio for r in ok if r.reliance_ratio is not None]
    rule_failures: Counter = Counter()
    for r in ok:
        rule_failures.update(r.d4k_failed_rules)
    unresolved: Counter = Counter()
    for r in ok:
        unresolved.update(r.repair_unresolved)

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_studies": len(runs), "n_assembled_ok": len(ok),
        "n_errors": len(runs) - len(ok),
        "structural_pass_rate": _rate(ok, lambda r: r.structural_passed),
        "d4k_pass_rate": _rate(ok, lambda r: r.d4k_passed),
        "core": dict(Counter(r.core_status for r in ok)),
        "auto_accept_coverage": (sum(r.n_auto_accept for r in ok) / total_fields
                                 if total_fields else None),
        "review_burden": (sum(r.n_review for r in ok) / total_fields if total_fields else None),
        "assembler_reliance_ratio_mean": (sum(reliance) / len(reliance) if reliance else None),
        "rule_failure_histogram": dict(rule_failures.most_common()),
        "repair_unresolved_histogram": dict(unresolved.most_common()),
        "realized_error_on_labelled_studies": (
            labelled.overall.realized_error if labelled.studies else None),
        "n_labelled_studies": len(labelled.studies),
        "n_labels": labelled.n_labels_total,
        "runs": [asdict(r) for r in runs],
    }


def _pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _dict_str(d: dict) -> str:
    return "; ".join(f"{k}: {v}" for k, v in d.items()) if d else "—"


def render_scoreboard(summary: dict) -> str:
    assembled_line = (f"{summary['n_assembled_ok']}/{summary['n_studies']} studies assembled "
                      f"without error ({summary['n_errors']} pipeline error(s)).")
    realized_line = (f"| Realized error (labelled studies) | "
                     f"{_pct(summary['realized_error_on_labelled_studies'])} "
                     f"(n={summary['n_labels']} labels, {summary['n_labelled_studies']} studies) |")
    lines = [
        "# Scoreboard", "",
        f"Generated {summary['generated_at']}. `usdm4` and rule-set pins: see `PINS.md`.",
        "",
        assembled_line,
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Structural pass rate | {summary['structural_pass_rate']} |",
        f"| d4k pass rate | {summary['d4k_pass_rate']} |",
        f"| CORE status (per study) | {_dict_str(summary['core'])} |",
        f"| Auto-accept coverage | {_pct(summary['auto_accept_coverage'])} |",
        f"| Review burden | {_pct(summary['review_burden'])} |",
        f"| Assembler reliance ratio (mean) | {_pct(summary['assembler_reliance_ratio_mean'])} |",
        realized_line,
        "",
    ]
    if summary["n_labelled_studies"] < 20:
        caveat = (
            "> **Small-sample caveat.** DESIGN.md §5 anticipates ~1,200 field-level labels "
            f"from ~20 protocols; only {summary['n_labels']} labels across "
            f"{summary['n_labelled_studies']} studies exist today (task 4.1). Realized error "
            "above describes that small set, not a general accuracy claim. There is no "
            "certified conformal auto-accept threshold yet (task 4.3) — too few calibration "
            "points — so `auto_accept` above still comes from the pre-Phase-4 hand-set "
            "confidence formula, not a statistically-bounded one.")
        lines += [caveat, ""]
    if summary["rule_failure_histogram"]:
        lines += ["## d4k rule failures across the corpus", "",
                 "| Rule | Studies failing |", "|---|---|"]
        lines += [f"| `{rule}` | {n} |" for rule, n in summary["rule_failure_histogram"].items()]
        lines += [""]
    if summary["repair_unresolved_histogram"]:
        lines += ["## Repair loop: rules the bounded loop could not resolve", "",
                 "| Rule | Studies |", "|---|---|"]
        lines += [f"| `{rule}` | {n} |"
                 for rule, n in summary["repair_unresolved_histogram"].items()]
        lines += [""]
    errors = [r for r in summary["runs"] if not r["ok"]]
    if errors:
        lines += ["## Studies that failed to run", "", *[
            f"* **{r['study_id']}**: {r['error'].splitlines()[0] if r['error'] else 'assembly failed'}"
            for r in errors], ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", action="store_true",
                        help="Also run the CDISC CORE gate (needs CDISC_LIBRARY_API_KEY).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only run the first N studies (default: all).")
    args = parser.parse_args()

    corpus = studies()
    if not corpus:
        print(f"No studies found under {CORPUS_ROOT}. Clone the corpus first:\n"
              f"  git clone --depth 1 https://github.com/data4knowledge/usdm_data.git "
              f"spikes/_work/usdm_data", file=sys.stderr)
        return 1
    if args.limit:
        corpus = corpus[:args.limit]

    print(f"Running {len(corpus)} studies (core={'on' if args.core else 'off'})...")
    runs = []
    for i, study in enumerate(corpus, start=1):
        r = run_one(study, args.core)
        runs.append(r)
        status = "OK" if r.ok else f"ERROR: {(r.error or '').splitlines()[0]}"
        print(f"  [{i}/{len(corpus)}] {study.study_id}: {status}")

    print("Scoring the 4 held-out labelled studies (task 4.1)...")
    labelled = run_eval()

    summary = summarize(runs, labelled)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    SCOREBOARD_PATH.write_text(render_scoreboard(summary), encoding="utf-8")

    print(f"\nStructural: {summary['structural_pass_rate']} | d4k: {summary['d4k_pass_rate']} | "
          f"auto-accept coverage: {_pct(summary['auto_accept_coverage'])}")
    print(f"Wrote {REPORT_PATH.relative_to(REPO_ROOT)} and {SCOREBOARD_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
