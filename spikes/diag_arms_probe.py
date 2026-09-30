import sys, glob
sys.path.insert(0, "src")
from usdm4_assure.extract.design import extract_design
from usdm4_assure.ingest.pdf import ingest
DDF = "C:/Users/2000205748/OneDrive - Hexaware Technologies/USDM_4_Docs/Digital Data Flow (Downstream)/from pfizer - Copy/Training Studies"
for st, ver in [("C5091017","2"), ("C4601003","5"), ("C4891001","4"), ("C4891002","3"), ("C4891006","4")]:
    pdf = glob.glob(f"{DDF}/{st}/input docs/Clinical Protocol - {ver} *.pdf")[0]
    doc = ingest(pdf)
    _, de = extract_design(doc, {}, None)
    print(st, [a["name"] for a in de.arms], de.arms_source[:60])
