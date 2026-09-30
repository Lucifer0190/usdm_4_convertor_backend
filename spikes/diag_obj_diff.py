import json, sys, glob
sys.path.insert(0, "src"); sys.path.insert(0, ".")
from usdm4_assure.eval.rubric import view_of
from run_benchmark import find_reference
DDF = __import__("pathlib").Path("C:/Users/2000205748/OneDrive - Hexaware Technologies/USDM_4_Docs/Digital Data Flow (Downstream)")
st = sys.argv[1]
ref = view_of(json.load(open(find_reference(DDF, st), encoding="utf-8")))
dl = view_of(json.load(open(f"data/out/cpe1/{st}/study.usdm.json", encoding="utf-8")))
print("REF objectives:", len(ref["objectives"]))
for o in ref["objectives"]: print(" O:", o[:90])
print("REF endpoints:", len(ref["endpoints"]))
for e in ref["endpoints"]: print(" E:", e[:90])
print("---DELIVERED---")
print("DEL objectives:", len(dl["objectives"]))
for o in dl["objectives"]: print(" O:", o[:90])
print("DEL endpoints:", len(dl["endpoints"]))
for e in dl["endpoints"]: print(" E:", e[:90])
