"""Does the real usdm4 assembler tolerate leaving the ERROR-severity fields actually
empty (rather than fabricated), once the structural (WARNING/INFO) gaps are still
filled? Uses the synthetic fixture. Runs sanitize() then re-blanks one ERROR field."""
import sys
sys.path.insert(0, "src")
sys.path.insert(0, ".")
from make_full_fixture import build
from usdm4_assure.assemble.fallback import assemble
from usdm4_assure.assemble.sanitize import sanitize
from usdm4_assure.assemble.study import _assembler_input
from usdm4_assure.extract.design import DesignExtract
from usdm4_assure.extract.eligibility import EligibilityExtract
from usdm4_assure.extract.objectives import ObjectivePair, ObjectivesExtract
from usdm4_assure.extract.soa.crossval import cross_validate
from usdm4_assure.extract.soa.methods import extract_pdfplumber, extract_pymupdf

pdf = build()
grid = cross_validate([extract_pdfplumber(pdf), extract_pymupdf(pdf)])
META = {"studyTitle": "A Phase 2 Study of Drug A", "studyAcronym": "DA-2",
        "protocolIdentifier": "DA-201", "studyVersionIdentifier": "2.0",
        "sponsorName": "Drug A Pharma", "studyPhase": "Phase 2"}
design = DesignExtract(intervention_model="Parallel",
                       arms=[{"name": "Drug A", "type": "Experimental"},
                             {"name": "Placebo", "type": "Placebo"}])
elig = EligibilityExtract(inclusion=["Adults."], exclusion=["Pregnancy."], age_min=18, age_max=75)
objs = ObjectivesExtract(items=[ObjectivePair("Evaluate efficacy.", "PASI 75.", "Primary")])


def trial(name, path, blank):
    raw, _ = _assembler_input(META, design, grid, elig, objs)
    clean, _ = sanitize(raw)
    node = clean
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = blank
    out = assemble(clean)
    print(f"{name}: ok={out.study_ok} dropped={out.dropped} "
          f"errors={out.errors[:2]}")


trial("phase=''", ("study_design", "trial_phase"), "")
trial("intervention_model=''", ("study_design", "intervention_model"), "")
trial("inclusion=[]", ("population", "inclusion_exclusion", "inclusion"), [])
trial("protocol id=''", ("identification", "identifiers", 0, "identifier"), "")
trial("sponsor name=''", ("identification", "identifiers", 0, "scope", "non_standard", "name"), "")
trial("title=''", ("identification", "titles", "official"), "")

trial("doc version=''", ("document", "document", "version"), "")
trial("study version=''", ("study", "version"), "")
trial("version_date=''", ("document", "document", "version_date"), "")
trial("sections=[]", ("document", "sections"), [])
trial("design rationale=''", ("study_design", "rationale"), "")
trial("study rationale=''", ("study", "rationale"), "")
trial("sponsor name='' (non_standard.name)", ("identification", "identifiers", 0, "scope", "non_standard", "name"), "")
