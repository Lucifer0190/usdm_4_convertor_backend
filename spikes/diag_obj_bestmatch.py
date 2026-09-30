import json, sys
sys.path.insert(0, "src"); sys.path.insert(0, ".")
from usdm4_assure.eval.rubric import view_of, _jaccard
from run_benchmark import find_reference
DDF = __import__("pathlib").Path("C:/Users/2000205748/OneDrive - Hexaware Technologies/USDM_4_Docs/Digital Data Flow (Downstream)")
st = sys.argv[1]
ref = view_of(json.load(open(find_reference(DDF, st), encoding="utf-8")))["endpoints"]
dl = view_of(json.load(open(f"data/out/cpe1/{st}/study.usdm.json", encoding="utf-8")))["endpoints"]
for r in ref:
    best = max(((_jaccard(r, d), d) for d in dl), default=(0, ""))
    flag = "OK" if best[0] >= 0.5 else "MISS"
    print(f"{flag} {best[0]:.2f} | {r[:70]!r} -> {best[1][:70]!r}")
