import sys, glob, re
sys.path.insert(0, "src")
from usdm4_assure.ingest.pdf import ingest
DDF = "C:/Users/2000205748/OneDrive - Hexaware Technologies/USDM_4_Docs/Digital Data Flow (Downstream)/from pfizer - Copy/Training Studies"
LABELS = ["US IND Number", "IND Number", "EU CT Number", "EudraCT Number",
         "ClinicalTrials.gov ID", "Pediatric Investigational Plan Number",
         "Study Intervention Number"]
import pathlib
studies = sorted({pathlib.Path(p).name for p in glob.glob(f"{DDF}/*")})[:15]
for st in studies:
    pdfs = sorted(glob.glob(f"{DDF}/{st}/input docs/Clinical Protocol - 0*.pdf"))
    if not pdfs: continue
    doc = ingest(pdfs[0])
    lines = [ln.strip() for b in doc.blocks if b.page <= 2 for ln in b.text.splitlines() if ln.strip()]
    found = {lab: next((ln for ln in lines if lab.lower() in ln.lower()), None) for lab in LABELS}
    print(st, {k: v for k, v in found.items() if v})
