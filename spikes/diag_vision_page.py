"""Re-read one page with the vision reader (cached) and show the raw answer."""
import sys, glob
sys.path.insert(0, "src")
import pymupdf
from usdm4_assure.extract.soa import vision_table as vt
from usdm4_assure.llm.router import get_role_llm
DDF = "C:/Users/2000205748/OneDrive - Hexaware Technologies/USDM_4_Docs/Digital Data Flow (Downstream)/from pfizer - Copy/Training Studies"
st, ver, page = sys.argv[1], sys.argv[2], int(sys.argv[3])
pdf = glob.glob(f"{DDF}/{st}/input docs/Clinical Protocol - {ver} *.pdf")[0]
doc = pymupdf.open(pdf); img, text = vt._render(doc, page)
prompt = vt._PROMPT_FILE.read_text(encoding="utf-8").replace("{page_text}", text[:vt._MAX_PAGE_TEXT])
raw = get_role_llm("vision").complete_vision(img, prompt, max_tokens=vt._MAX_TOKENS)
print(len(raw)); print(raw[:600]); print("...", raw[-300:]); print("parsed:", vt._parse(raw, page) is not None)
