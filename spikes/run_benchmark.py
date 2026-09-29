#!/usr/bin/env python3
"""Multi-study accuracy benchmark against hand-corrected Pfizer USDMs.

Runs ``run_full()`` on the latest protocol version of each golden study and scores
the delivered USDM against its reference with :mod:`usdm4_assure.eval.rubric`
(items matched / (reference items + spurious items)). Deterministic by default —
no LLM calls, no cost; ``--llm`` turns the LLM readers on.

The data lives outside the repo (Pfizer's packet), so its location is an argument:

    .venv/Scripts/python.exe spikes/run_benchmark.py --ddf-root "<Digital Data Flow (Downstream)>" \\
        --out <scratch dir> [--llm] [--studies C5091017 C4891001]

The reference for a study is ``from team (ideal)/*<study>*.json``; the protocol is the
``Clinical Protocol - N`` whose N equals the reference's version number (USDM v4.0 of a
study is its amendment-4 protocol). Writes ``benchmark.json`` and ``benchmark.md`` to
``--out`` and, with ``--publish``, ``spikes/reports/benchmark.md``.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from usdm4_assure.eval.rubric import score_study, view_of  # noqa: E402

STUDIES = ["C5091017", "C4601003", "C4891001", "C4891002", "C4891006", "C4891023",
           "C4891024", "C4891026"]


def find_reference(ddf: Path, study: str) -> Path:
    hits = sorted((ddf / "from team (ideal)").glob(f"*{study}*.json"))
    if not hits:
        raise FileNotFoundError(f"no reference USDM for {study}")
    return hits[0]


def find_protocol(ddf: Path, study: str, version: int) -> Path:
    folder = ddf / "from pfizer - Copy" / "Training Studies" / study / "input docs"
    for p in folder.glob("Clinical Protocol - *.pdf"):
        m = re.search(r"Protocol - (\d+)", p.name)
        if m and int(m.group(1)) == version and p.stat().st_size > 0:
            return p
    raise FileNotFoundError(f"no protocol version {version} for {study}")


def render_md(rows: list[dict], mode: str) -> str:
    cats = ["scalars", "identifiers", "arms", "interventions", "criteria", "objectives",
            "endpoints", "estimands", "epochs", "encounters", "activities", "marks", "vendors"]
    total_m = sum(r["matched"] for r in rows)
    total_ref = sum(r["reference"] for r in rows)
    total_sp = sum(r["spurious"] for r in rows)
    lines = [f"# Benchmark - {mode}", "",
             f"Studies: {len(rows)} | reference items {total_ref} | matched {total_m} | "
             f"spurious {total_sp}", "",
             f"**Accuracy (matched / (reference + spurious)): {100 * total_m / max(1, total_ref + total_sp):.1f}%**"
             f"  |  recall {100 * total_m / max(1, total_ref):.1f}%", "",
             "| Study | Accuracy | Recall | Matched | Reference | Spurious | Seconds |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['study']} | {100 * r['accuracy']:.1f}% | {100 * r['recall']:.1f}% | "
                     f"{r['matched']} | {r['reference']} | {r['spurious']} | {r['seconds']:.0f} |")
    lines += ["", "## By category (all studies pooled)", "",
              "| Category | Matched | Reference | Delivered | Recall |", "|---|---:|---:|---:|---:|"]
    for c in cats:
        m = sum(r["categories"].get(c, {}).get("matched", 0) for r in rows)
        ref = sum(r["categories"].get(c, {}).get("reference", 0) for r in rows)
        d = sum(r["categories"].get(c, {}).get("delivered", 0) for r in rows)
        if ref:
            lines.append(f"| {c} | {m} | {ref} | {d} | {100 * m / ref:.0f}% |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ddf-root", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--studies", nargs="*", default=STUDIES)
    ap.add_argument("--llm", action="store_true", help="enable the LLM readers (costs money)")
    ap.add_argument("--reuse", action="store_true",
                    help="score existing <out>/<study>/study.usdm.json instead of re-running")
    ap.add_argument("--publish", action="store_true", help="also write spikes/reports/benchmark.md")
    args = ap.parse_args()

    if not args.llm:
        os.environ["USDM4_NO_LLM"] = "1"
    from usdm4_assure.pipeline import run_full

    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for study in args.studies:
        ref_path = find_reference(args.ddf_root, study)
        reference = json.loads(ref_path.read_text(encoding="utf-8"))
        version = int(re.findall(r"\d+", str(view_of(reference)["scalars"].get("version", "0")))[0])
        pdf = find_protocol(args.ddf_root, study, version)
        out_dir = args.out / study
        t0 = time.time()
        try:
            if not (args.reuse and (out_dir / "study.usdm.json").exists()):
                run_full(pdf, out_dir=out_dir, use_slm=False)
            delivered = json.loads((out_dir / "study.usdm.json").read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 — a failed study is a 0, never a skipped row
            print(f"{study}: FAILED {type(exc).__name__}: {exc}")
            delivered = {"study": {"versions": [{"studyDesigns": [{}]}]}}
        score = score_study(delivered, reference)
        row = {"study": study, "protocol": pdf.name, "seconds": time.time() - t0,
               "accuracy": score.accuracy, "recall": score.recall, "matched": score.matched,
               "reference": score.reference, "spurious": score.spurious,
               "categories": {k: vars(v) for k, v in score.categories.items()}}
        rows.append(row)
        print(f"{study}: accuracy {100 * score.accuracy:.1f}%  recall {100 * score.recall:.1f}%  "
              f"({score.matched}/{score.reference}, spurious {score.spurious})  {pdf.name}", flush=True)

    mode = "LLM readers on" if args.llm else "deterministic only (no LLM)"
    md = render_md(rows, mode)
    (args.out / "benchmark.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (args.out / "benchmark.md").write_text(md, encoding="utf-8")
    if args.publish:
        (ROOT / "spikes" / "reports" / "benchmark.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
