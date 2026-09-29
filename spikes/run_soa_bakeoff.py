#!/usr/bin/env python3
"""SoA reader bake-off (PLAN.md tasks C-2 / C-3): geometry vs vision on the same pages.

For each study the schedule pages are found once (the SoA slot, the group the geometry reader
uses), then each reader reads exactly those pages and is scored on the SoA categories only
(epochs, visits, activities, marks) with ``eval.rubric.score_grid``. The vision reader calls
the ``vision`` model role (costs money; responses are cached, so a re-run is free).

    python spikes/run_soa_bakeoff.py --ddf-root "<Digital Data Flow (Downstream)>" --out <dir>
        [--set train] [--readers geometry vision] [--max-pages 12]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "spikes"))

from run_benchmark import find_protocol, find_reference

from usdm4_assure.eval.rubric import SOA_CATEGORIES, score_grid, view_of
from usdm4_assure.eval.split import HeldOutGuard, studies_for


def schedule_pages(pdf: Path) -> list[int]:
    from usdm4_assure.extract.soa.geometry import read_first_schedule
    from usdm4_assure.ingest.pdf import ingest
    from usdm4_assure.sections.graph import build_graph
    from usdm4_assure.sections.slots import slot_windows, strip_furniture

    doc = strip_furniture(ingest(pdf))
    groups = [w.pages for w in slot_windows(doc, build_graph(doc, pdf), "soa")]
    _, used = read_first_schedule(pdf, groups)
    return groups[max(used, 0)] if groups else []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ddf-root", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--set", dest="which", default="train", choices=["train", "heldout", "all"])
    ap.add_argument("--confirm-heldout", action="store_true")
    ap.add_argument("--readers", nargs="+", default=["geometry", "vision"])
    ap.add_argument("--max-pages", type=int, default=12, help="cap on pages sent to vision")
    args = ap.parse_args()
    try:
        studies = studies_for(args.which, confirm_heldout=args.confirm_heldout)
    except HeldOutGuard as exc:
        print(f"refused: {exc}")
        return 2

    from usdm4_assure.extract.soa.geometry import read_soa_geometry
    from usdm4_assure.extract.soa.vision_table import read_soa_vision
    from usdm4_assure.llm.router import get_role_llm

    vision = get_role_llm("vision")
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for study in studies:
        reference = json.loads(find_reference(args.ddf_root, study).read_text(encoding="utf-8"))
        version = int(re.findall(r"\d+", str(view_of(reference)["scalars"].get("version", "0")))[0])
        pdf = find_protocol(args.ddf_root, study, version)
        pages = schedule_pages(pdf)
        for reader in args.readers:
            t0 = time.time()
            extra: dict = {}
            if reader == "geometry":
                grid = read_soa_geometry(pdf, pages)
            else:
                grid, report = read_soa_vision(pdf, pages[:args.max_pages], vision)
                extra = {"pages_failed": report.failed, "grounded": round(report.grounded_share, 3)}
            if grid is None:
                print(f"{study} {reader}: no grid {extra}", flush=True)
                rows.append({"study": study, "reader": reader, "accuracy": 0.0, "categories": {},
                             **extra})
                continue
            s = score_grid(grid, reference)
            row = {"study": study, "reader": reader, "pages": pages, "seconds": round(time.time() - t0),
                   "accuracy": s.accuracy, "recall": s.recall, "matched": s.matched,
                   "reference": s.reference, "spurious": s.spurious, "stats": grid.stats(),
                   "categories": {k: vars(v) for k, v in s.categories.items()}, **extra}
            rows.append(row)
            (args.out / f"{study}.{reader}.grid.json").write_text(json.dumps(
                {"epochs": grid.epochs, "visits": grid.visits, "activities": grid.activities,
                 "cells": sorted(grid.cells)}, indent=1), encoding="utf-8")
            print(f"{study} {reader}: SoA accuracy {100 * s.accuracy:.1f}% recall "
                  f"{100 * s.recall:.1f}% {grid.stats()} {extra}", flush=True)

    lines = ["# SoA bake-off", "", "| Study | Reader | SoA accuracy | Recall | "
             + " | ".join(SOA_CATEGORIES) + " |", "|---|---|---:|---:|" + "---:|" * len(SOA_CATEGORIES)]
    for r in rows:
        cats = " | ".join(f"{c['matched']}/{c['reference']} ({c['delivered']})"
                          if (c := r["categories"].get(k)) else "-" for k in SOA_CATEGORIES)
        lines.append(f"| {r['study']} | {r['reader']} | {100 * r['accuracy']:.1f}% | "
                     f"{100 * r.get('recall', 0):.1f}% | {cats} |")
    lines += ["", "## Pooled", "", "| Reader | SoA accuracy | Recall |", "|---|---:|---:|"]
    for reader in args.readers:
        rs = [r for r in rows if r["reader"] == reader]
        m = sum(r.get("matched", 0) for r in rs)
        ref = sum(r.get("reference", 0) for r in rs)
        sp = sum(r.get("spurious", 0) for r in rs)
        lines.append(f"| {reader} | {100 * m / max(1, ref + sp):.1f}% | {100 * m / max(1, ref):.1f}% |")
    md = "\n".join(lines) + "\n"
    (args.out / "bakeoff.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    (args.out / "bakeoff.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
