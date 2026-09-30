"""Per-page view of the SoA section: tables built, columns, header text."""
import sys, glob
sys.path.insert(0, "src")
import pymupdf
from usdm4_assure.ingest.pdf import ingest
from usdm4_assure.sections.graph import build_graph
from usdm4_assure.sections.slots import slot_windows, strip_furniture
from usdm4_assure.extract.soa import geometry as g
DDF = "C:/Users/2000205748/OneDrive - Hexaware Technologies/USDM_4_Docs/Digital Data Flow (Downstream)/from pfizer - Copy/Training Studies"
st, ver = sys.argv[1], sys.argv[2]
pdf = glob.glob(f"{DDF}/{st}/input docs/Clinical Protocol - {ver} *.pdf")[0]
doc = strip_furniture(ingest(pdf)); graph = build_graph(doc, pdf)
groups = [w.pages for w in slot_windows(doc, graph, "soa")]
print("groups", groups)
d = pymupdf.open(pdf)
for pno in sorted({p for gp in groups for p in gp}):
    t = g._build_table(d[pno - 1], pno)
    if t is None:
        print(pno, "no table"); continue
    hdr = []
    for r in range(min(4, len(t.row_edges) - 1)):
        y0, y1 = t.row_edges[r], t.row_edges[r + 1]
        cells = []
        for c in range(min(6, len(t.col_edges) - 1)):
            cells.append(g._join(g._cell_lines(t.lines, t.col_edges[c], t.col_edges[c + 1], y0, y1))[:28])
        hdr.append(" | ".join(cells))
    print(pno, "cols", len(t.col_edges) - 1, "rows", len(t.row_edges) - 1)
    for h in hdr: print("     ", h)
