"""Study arms extraction (C2): the comma/ratio-list parser and the bulleted-label
parser it now tries first."""
from __future__ import annotations

from usdm4_assure.contracts import Document
from usdm4_assure.extract.design import _bulleted_arms, _parse_arms, extract_design


def _names(arms: list[dict]) -> list[str]:
    return [a["name"] for a in arms]


# --- bulleted-label arms (new) ----------------------------------------------------- #
def test_a_bulleted_arm_list_split_across_paragraphs_is_read_in_full():
    text = (
        "Participants will be randomly assigned on a 1:1 basis to:\n"
        "•   Arm A: (Investigational Arm; n ≈ 280). Participants will receive "
        "ARV-471 200 mg orally, once daily.\n"
        "ARV-471 Protocol C4891001 Final Protocol, Amendment 4\n"        # running footer
        "PFIZER CONFIDENTIAL CT02-GSOP Clinical Protocol Template\n"
        "•   Arm B: (Comparator Arm; n ≈ 280). Participants will receive "
        "fulvestrant 500 mg intramuscularly.")
    arms, src = _bulleted_arms(text)
    assert _names(arms) == ["Arm A", "Arm B"] and src == "bulleted arm list"


def test_a_dose_escalation_list_uses_the_wingdings_bullet_and_no_colon():
    text = ("Approximately 50 participants will be randomly assigned on a 1:1 basis to:\n"
           " Dose Level 1 (n ≈ 25). Participants will receive vepdegestrant 200 mg.\n"
           " Dose Level 2 (n ≈ 25). Participants will receive vepdegestrant 200 mg.")
    arms, _ = _bulleted_arms(text)
    assert _names(arms) == ["Dose Level 1", "Dose Level 2"]


def test_a_later_unrelated_enumeration_is_not_merged_into_the_first():
    """A protocol can name two different things with bulleted labels (a dose-escalation
    block, then a separate later comparison) — only the first family is taken."""
    text = (" Dose Level 1 (n ≈ 25). Description.\n"
           " Dose Level 2 (n ≈ 25). Description.\n"
           "In the randomized comparison:\n"
           "• Arm A: (Investigational Arm). Description.\n"
           "• Arm B: (Comparator Arm). Description.")
    arms, _ = _bulleted_arms(text)
    assert _names(arms) == ["Dose Level 1", "Dose Level 2"]


def test_a_single_bulleted_label_is_not_enough_to_be_an_arm_list():
    arms, src = _bulleted_arms("• Part A (dose escalation). Only one part is bulleted.")
    assert arms == [] and src == ""


def test_no_bulleted_labels_returns_nothing():
    assert _bulleted_arms("There is no bulleted list of arms in this paragraph at all.") == ([], "")


# --- comma/ratio-list arms (existing) stays the fallback ---------------------------- #
def test_extract_design_falls_back_to_the_comma_list_when_nothing_is_bulleted():
    text = ("Participants will be randomized 1:1:1 to arms: Ibuzatrelvir, or Placebo.")
    doc = Document(source=None, blocks=[], full_text=text)
    _, de = extract_design(doc, {}, None)
    assert _names(de.arms) == ["Ibuzatrelvir", "Placebo"]
    assert de.arms_source.startswith("arms:")


def test_extract_design_prefers_a_bulleted_list_over_the_comma_fallback():
    text = ("Participants will be randomized on a 1:1 basis to:\n"
           "• Arm A: (Investigational Arm). Receives drug X.\n"
           "• Arm B: (Comparator Arm). Receives drug Y.")
    doc = Document(source=None, blocks=[], full_text=text)
    _, de = extract_design(doc, {}, None)
    assert _names(de.arms) == ["Arm A", "Arm B"]
    assert de.arms_source == "bulleted arm list"


def test_parse_arms_unaffected_by_the_new_path():
    arms, src = _parse_arms("Subjects are randomized 2:1 to groups: Drug, or Placebo.")
    assert _names(arms) == ["Drug", "Placebo"]
    assert src.startswith("groups:")
