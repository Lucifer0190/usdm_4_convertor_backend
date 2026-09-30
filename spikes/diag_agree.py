"""Does geometry/vision agreement predict a correct mark? Precision of agreed vs single-reader marks."""
import json, re, sys, glob
sys.path.insert(0, "src"); sys.path.insert(0, "spikes")
from usdm4_assure.eval.rubric import view_of, _jaccard
from usdm4_assure.extract.soa.geometry import _visit_key
from run_benchmark import find_reference
DDF = __import__("pathlib").Path("C:/Users/2000205748/OneDrive - Hexaware Technologies/USDM_4_Docs/Digital Data Flow (Downstream)")
akey = lambda s: re.sub(r"\W+", "", s.lower())
tot = {"both": [0, 0], "geometry only": [0, 0], "vision only": [0, 0]}
for st in ["C5091017", "C4601003", "C4891001", "C4891002", "C4891006"]:
    ref = view_of(json.load(open(find_reference(DDF, st), encoding="utf-8")))["marks"]
    if not ref: continue
    grids = {r: json.load(open(f"data/out/bake3/{st}.{r}.grid.json", encoding="utf-8")) for r in ("geometry", "vision")}
    marks = {r: {(_visit_key(g["visits"][v]), akey(g["activities"][a])): (g["visits"][v], g["activities"][a]) for a, v in g["cells"]} for r, g in grids.items()}
    def correct(m): return any(min(_jaccard(m[0], r[0]), _jaccard(m[1], r[1])) >= 0.6 for r in ref)
    G, V = set(marks["geometry"]), set(marks["vision"])
    for name, keys, src in (("both", G & V, "geometry"), ("geometry only", G - V, "geometry"), ("vision only", V - G, "vision")):
        ok = sum(correct(marks[src][k]) for k in keys); tot[name][0] += ok; tot[name][1] += len(keys)
        print(st, name, f"{ok}/{len(keys)}")
for k, (ok, n) in tot.items(): print(f"POOLED {k}: {ok}/{n} correct = {100*ok/max(1,n):.0f}%")
