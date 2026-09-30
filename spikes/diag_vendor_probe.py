import sys, glob
sys.path.insert(0, "src")
from usdm4_assure.ingest.pdf import ingest
DDF = "C:/Users/2000205748/OneDrive - Hexaware Technologies/USDM_4_Docs/Digital Data Flow (Downstream)/from pfizer - Copy/Training Studies"
st, ver = sys.argv[1], sys.argv[2]
pdf = glob.glob(f"{DDF}/{st}/input docs/Clinical Protocol - {ver} *.pdf")[0]
doc = ingest(pdf)
for b in doc.blocks:
    if any(k in b.text for k in ("Central Laboratory", "Central Imaging", "Central ECG",
                                                  "IRT", "eCOA", "Florence", "Vendor", "NCT0", "EudraCT",
                                                  "EU CT", "CRO", "Contract Research")):
        print(b.page, repr(b.text[:200]))
