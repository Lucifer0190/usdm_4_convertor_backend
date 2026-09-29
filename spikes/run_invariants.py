#!/usr/bin/env python3
"""Generalisation check over the whole Pfizer packet, with no labels.

Runs the section, schedule-of-activities, eligibility and objectives readers on every
protocol PDF under ``<ddf-root>/from pfizer - Copy/Training Studies`` (latest version of
each study by default, ``--all-versions`` for all 204) and reports how often each
structural invariant (``eval/invariants.py``) holds. A failing invariant on a protocol
is a layout family the readers do not handle; the report lists the failing files so the
fix can be made once, for all of them.

    .venv/Scripts/python.exe spikes/run_invariants.py --ddf-root "<Digital Data Flow (Downstream)>" \
        --out <scratch dir> [--all-versions] [--workers 4]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _run(pdf: str) -> dict:
    from usdm4_assure.eval.invariants import check_protocol
    try:
        r = check_protocol(pdf)
        r["study"] = Path(pdf).parents[1].name
        return r
    except Exception:  # noqa: BLE001 - a crash is a failure to report, not to hide
        return {"file": Path(pdf).name, "study": Path(pdf).parents[1].name,
                "error": traceback.format_exc()[-400:]}


def protocols(root: Path, all_versions: bool) -> list[Path]:
    packet = root / "from pfizer - Copy" / "Training Studies"
    found: dict[str, list[tuple[int, Path]]] = defaultdict(list)
    for p in packet.glob("*/input docs/Clinical Protocol - *.pdf"):
        m = re.search(r"Protocol - (\d+)", p.name)
        if m and p.stat().st_size > 0:
            found[p.parents[1].name].append((int(m.group(1)), p))
    out: list[Path] = []
    for study, items in sorted(found.items()):
        items.sort()
        out += [p for _, p in items] if all_versions else [items[-1][1]]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ddf-root", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--all-versions", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    files = protocols(args.ddf_root, args.all_versions)
    if args.limit:
        files = files[:args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"{len(files)} protocols", flush=True)
    results = []
    with Pool(args.workers) as pool:
        for i, r in enumerate(pool.imap_unordered(_run, [str(f) for f in files])):
            results.append(r)
            if i % 10 == 0:
                print(i, flush=True)
    (args.out / "invariants.json").write_text(json.dumps(results, indent=1), encoding="utf-8")

    ok = [r for r in results if "error" not in r]
    lines = [f"# Invariants over {len(results)} protocols ({len(results) - len(ok)} crashed)", ""]
    for group in ("slots", "soa", "eligibility", "objectives"):
        lines += [f"## {group}", "", "| Invariant | Holds | Rate |", "|---|---:|---:|"]
        names = sorted({k for r in ok for k in r.get(group, {})})
        for n in names:
            held = sum(1 for r in ok if r.get(group, {}).get(n))
            lines.append(f"| {n} | {held}/{len(ok)} | {100 * held / max(1, len(ok)):.0f}% |")
        lines.append("")
    lines += ["## Protocols failing at least one SoA invariant", ""]
    for r in sorted(ok, key=lambda r: r["file"]):
        bad = [k for k, v in r["soa"].items() if not v]
        if bad:
            lines.append(f"- {r['study']} / {r['file']}: {', '.join(bad)}  {r.get('soa_stats')}")
    lines += ["", "## Crashes", ""] + [f"- {r['study']} / {r['file']}: {r['error']!r}"
                                       for r in results if "error" in r]
    md = "\n".join(lines) + "\n"
    (args.out / "invariants.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
