import sys, glob
sys.path.insert(0, "src")
from usdm4_assure.extract.objectives_table import read_objectives_table
from usdm4_assure.ingest.pdf import ingest
from usdm4_assure.sections.graph import build_graph
from usdm4_assure.sections.slots import slot_windows, strip_furniture
DDF = "C:/Users/2000205748/OneDrive - Hexaware Technologies/USDM_4_Docs/Digital Data Flow (Downstream)/from pfizer - Copy/Training Studies"
st, ver = sys.argv[1], sys.argv[2]
pdf = glob.glob(f"{DDF}/{st}/input docs/Clinical Protocol - {ver} *.pdf")[0]
doc = strip_furniture(ingest(pdf)); graph = build_graph(doc, pdf)
win = [w.pages for w in slot_windows(doc, graph, "objectives")]
print("pages", win)
rows = read_objectives_table(pdf, win[0] if win else None)
for r in rows[:30]:
    print(r.tier, "|", r.level, "|", (r.objective or "")[:60], "|", (r.endpoints or [])[:2])
