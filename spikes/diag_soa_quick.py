"""Run the geometry reader alone on one study and print the grid."""
import sys, glob
sys.path.insert(0, "src")
from usdm4_assure.ingest.pdf import ingest
from usdm4_assure.sections.graph import build_graph
from usdm4_assure.sections.slots import slot_windows, strip_furniture
from usdm4_assure.extract.soa.geometry import read_first_schedule
DDF = "C:/Users/2000205748/OneDrive - Hexaware Technologies/USDM_4_Docs/Digital Data Flow (Downstream)/from pfizer - Copy/Training Studies"
st, ver = sys.argv[1], sys.argv[2]
pdf = glob.glob(f"{DDF}/{st}/input docs/Clinical Protocol - {ver} *.pdf")[0]
doc = strip_furniture(ingest(pdf)); graph = build_graph(doc, pdf)
grid, used = read_first_schedule(pdf, [w.pages for w in slot_windows(doc, graph, "soa")])
print(grid.stats())
for e, v in zip(grid.epochs, grid.visits): print(f"  {e[:30]:30} | {v[:70]}")
