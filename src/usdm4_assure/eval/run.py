"""Routing on/off comparison harness (task 3.7, DEVPLAN.md §3-C, PLAN.md §8.4).

Runs :func:`usdm4_assure.pipeline.run_full` twice per protocol — once with
section-graph routing (task 3.4-3.6) enabled, once with it off, i.e. every
extractor reading the whole document unscoped — and diffs the two runs'
:class:`~usdm4_assure.contracts.AssuredField` outputs field by field. This is
the Phase 3 exit measurement: a delta with routing on vs. off, and the number
of prohibited-scope leaks routing caught (``tests/test_scope_leak.py``
demonstrates one directly; this harness looks for the same signature —
a value or decision that changed — across the whole corpus).

Not a label-based scorer: there is no ground truth here, only routing-on vs.
routing-off disagreement. Phase 4 (task 4.1) adds frozen per-field labels and
a real scorer; until then, "did routing change anything, and in domains where
scope leaks are plausible" is the available signal.

Usage::

    .venv/Scripts/python -m usdm4_assure.eval.run [--limit N] [--out DIR]

Writes ``<out>/summary.json``, ``<out>/summary.md``, and one
``<out>/<study_id>.diff.json`` per study.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

from usdm4_assure.contracts import AssuredField
from usdm4_assure.eval.corpus import CORPUS_ROOT, Study, studies
from usdm4_assure.pipeline import run_full

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = REPO_ROOT / "spikes" / "reports" / "routing_eval"


@dataclass
class FieldDiff:
    domain: str
    field: str
    value_changed: bool
    decision_changed: bool
    routed_value: str | None
    unrouted_value: str | None
    routed_decision: str
    unrouted_decision: str


@dataclass
class StudyResult:
    study_id: str
    ok: bool
    error: str | None = None
    fields_compared: int = 0
    fields_changed: int = 0
    scope_findings: int = 0
    changed: list[FieldDiff] = field(default_factory=list)


def _by_key(fields: list[AssuredField]) -> dict[tuple[str, str], AssuredField]:
    return {(a.domain, a.field): a for a in fields}


def diff_fields(routed: list[AssuredField], unrouted: list[AssuredField]) -> list[FieldDiff]:
    """Field-by-field diff, keyed on (domain, field) so same-named fields in
    different domains never collide."""
    r, u = _by_key(routed), _by_key(unrouted)
    out = []
    for key in sorted(set(r) | set(u)):
        ra, ua = r.get(key), u.get(key)
        rv = ra.value if ra else None
        uv = ua.value if ua else None
        rd = ra.decision.value if ra else "absent"
        ud = ua.decision.value if ua else "absent"
        if rv != uv or rd != ud:
            out.append(FieldDiff(domain=key[0], field=key[1], value_changed=rv != uv,
                                 decision_changed=rd != ud, routed_value=rv, unrouted_value=uv,
                                 routed_decision=rd, unrouted_decision=ud))
    return out


def _all_assured(result) -> list[AssuredField]:
    return (result.assured_meta + result.assured_design
            + result.assured_eligibility + result.assured_objectives)


def compare_study(study: Study, out_dir: Path) -> StudyResult:
    """Run both arms for one study, diff them, and write the per-study JSON."""
    try:
        routed = run_full(study.pdf_path, out_dir=out_dir / study.study_id / "routed",
                          routing=True)
        unrouted = run_full(study.pdf_path, out_dir=out_dir / study.study_id / "unrouted",
                            routing=False)
    except Exception as exc:  # noqa: BLE001 — a broken study must not stop the corpus run
        return StudyResult(study.study_id, ok=False,
                           error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}")

    changed = diff_fields(_all_assured(routed), _all_assured(unrouted))
    total = len({(a.domain, a.field) for a in _all_assured(routed) + _all_assured(unrouted)})
    scope_findings = sum(f.kind.value == "scope" for f in routed.findings)
    res = StudyResult(study.study_id, ok=True, fields_compared=total,
                      fields_changed=len(changed), scope_findings=scope_findings,
                      changed=changed)
    (out_dir / f"{study.study_id}.diff.json").write_text(
        json.dumps(asdict(res), indent=2, default=str), encoding="utf-8")
    return res


def _summary_md(results: list[StudyResult]) -> str:
    ok = [r for r in results if r.ok]
    lines = ["# Routing on/off comparison\n",
             f"{len(ok)}/{len(results)} studies ran cleanly under both arms.\n",
             "| Study | Fields compared | Changed | Scope findings (routed) |",
             "|---|---|---|---|"]
    for r in results:
        if not r.ok:
            lines.append(f"| {r.study_id} | ERROR | — | — |")
            continue
        lines.append(f"| {r.study_id} | {r.fields_compared} | {r.fields_changed} | "
                     f"{r.scope_findings} |")
    if ok:
        total_changed = sum(r.fields_changed for r in ok)
        total_compared = sum(r.fields_compared for r in ok)
        total_scope = sum(r.scope_findings for r in ok)
        totals = (f"**Totals:** {total_changed}/{total_compared} fields changed by "
                 f"routing; {total_scope} scope finding(s) across the corpus.")
        lines += ["", totals]
    errors = [r for r in results if not r.ok]
    if errors:
        lines += ["", "## Errors", ""]
        lines += [f"* **{r.study_id}**: {r.error.splitlines()[0]}" for r in errors]
    return "\n".join(lines) + "\n"


def run(study_list: list[Study], out_dir: Path = DEFAULT_OUT) -> list[StudyResult]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results = [compare_study(s, out_dir) for s in study_list]
    (out_dir / "summary.json").write_text(
        json.dumps([asdict(r) for r in results], indent=2, default=str), encoding="utf-8")
    (out_dir / "summary.md").write_text(_summary_md(results), encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="Only run the first N studies (default: all).")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"Output directory (default: {DEFAULT_OUT.relative_to(REPO_ROOT)}).")
    args = parser.parse_args()

    study_list = studies()
    if not study_list:
        print(f"No studies found under {CORPUS_ROOT}. Clone the corpus first:\n"
              f"  git clone --depth 1 https://github.com/data4knowledge/usdm_data.git "
              f"spikes/_work/usdm_data", file=sys.stderr)
        return 1
    if args.limit:
        study_list = study_list[:args.limit]

    print(f"Comparing {len(study_list)} studies (routing on vs. off)...")
    results = run(study_list, args.out)
    for r in results:
        status = "OK" if r.ok else f"ERROR: {r.error.splitlines()[0]}"
        print(f"  {r.study_id}: {status}" + ("" if not r.ok else
              f" — {r.fields_changed}/{r.fields_compared} fields changed, "
              f"{r.scope_findings} scope finding(s)"))
    try:
        shown = args.out.relative_to(REPO_ROOT)
    except ValueError:
        shown = args.out
    print(f"\nWrote {shown}/summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
