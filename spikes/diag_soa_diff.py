import json, sys, glob
sys.path.insert(0, "src")
from usdm4_assure.eval.rubric import view_of
DDF = "C:/Users/2000205748/OneDrive - Hexaware Technologies/USDM_4_Docs/Digital Data Flow (Downstream)"
for st in sys.argv[1:]:
    ref = json.load(open(glob.glob(f"{DDF}/from team (ideal)/*{st}*.json")[0], encoding="utf-8"))
    dl = json.load(open(f"data/out/cpd1/{st}/study.usdm.json", encoding="utf-8"))
    R, D = view_of(ref), view_of(dl)
    print("=====", st)
    for k in ("epochs", "encounters"):
        print(k, "REF:", R.get(k)); print(k, "DEL:", D.get(k))
    print("activities REF:", R.get("activities")[:25]); print("activities DEL:", D.get("activities")[:25])
    print("marks REF sample:", list(R.get("marks", []))[:8]); print("marks DEL sample:", list(D.get("marks", []))[:8])
