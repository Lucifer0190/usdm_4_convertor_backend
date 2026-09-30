import json, sys, glob
sys.path.insert(0, "src"); sys.path.insert(0, ".")
from usdm4_assure.eval.rubric import view_of
from run_benchmark import find_reference
DDF = __import__("pathlib").Path("C:/Users/2000205748/OneDrive - Hexaware Technologies/USDM_4_Docs/Digital Data Flow (Downstream)")
for st in ["C5091017", "C4601003", "C4891001", "C4891002", "C4891006"]:
    ref = json.load(open(find_reference(DDF, st), encoding="utf-8"))
    v = view_of(ref)
    print(st, "identifiers:", v["identifiers"])
    print(st, "vendors:", v["vendors"])
