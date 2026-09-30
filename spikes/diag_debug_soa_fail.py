import sys, json
sys.path.insert(0, "src"); sys.path.insert(0, ".")
from make_full_fixture import build as build_full
from usdm4_assure.assemble.study import build_full_study
from usdm4_assure.extract.design import DesignExtract
from usdm4_assure.extract.soa.crossval import cross_validate as cv
from usdm4_assure.extract.soa.methods import extract_pdfplumber as epp
from usdm4_assure.extract.soa.methods import extract_pymupdf as epm
pdf = build_full()
grid = cv([epp(pdf), epm(pdf)])
design = DesignExtract(intervention_model="Parallel",
                       arms=[{"name": "A", "type": "Experimental"},
                             {"name": "Placebo", "type": "Placebo Comparator"}])
study = build_full_study([], design, grid)
print("ok", study["ok"])
print("assembler_errors", study["assembler_errors"])
print("validation", json.dumps(study["validation"], indent=1)[:2000])
