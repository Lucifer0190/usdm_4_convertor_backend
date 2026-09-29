"""Eligibility criteria read from their own section (accuracy fix).

Items are found by *sequential* numbering (1., 2., 3. ...) inside the inclusion /
exclusion windows, so a stray "Day 28." or a sub-item "a." cannot start a
criterion, group headings are not glued onto the previous criterion, and the
count is checkable (numbering must be contiguous).
"""
from __future__ import annotations

from pathlib import Path

from usdm4_assure.contracts import Block, Document
from usdm4_assure.extract.eligibility import (
    age_range,
    extract_eligibility,
    split_numbered,
)


def _doc(*texts: str) -> Document:
    bl = [Block(text=t, page=1, bbox=(72.0, 100.0 + i * 20, 500.0, 112.0 + i * 20))
          for i, t in enumerate(texts)]
    return Document(source=Path("x.pdf"), blocks=bl, full_text="\n".join(texts))


INCLUSION = (
    "5.1. Inclusion Criteria\n"
    "Participants are eligible to be included in this study only if all of the following apply:\n"
    "Age and risk factors:\n"
    "1.   12 to <18 years of age, or \u226518 years of age of any weight at screening.\n"
    "2.   Presence of risk factors at screening based on age: a. 12 to 49 years with two risk "
    "factors; b. 50 years or older with one.\n"
    "Informed consent:\n"
    "3.   Capable of giving signed informed consent by Day 28. The consent form must be signed."
)


def test_split_numbered_uses_sequential_numbers_only():
    items = split_numbered(INCLUSION)
    assert len(items) == 3
    assert items[0].startswith("12 to <18 years of age")
    assert items[1].startswith("Presence of risk factors")
    assert "a. 12 to 49 years" in items[1]              # a sub-item stays inside its parent
    assert items[2].startswith("Capable of giving")
    assert "Day 28." in items[2]                        # "28." is not the start of item 28


def test_group_headings_are_not_glued_onto_the_previous_item():
    items = split_numbered(INCLUSION)
    assert not items[0].rstrip().endswith("Age and risk factors:")
    assert not items[1].rstrip().endswith("Informed consent:")


def test_intro_sentence_and_section_title_are_not_criteria():
    items = split_numbered(INCLUSION)
    assert not any("eligible to be included" in i for i in items)
    assert not any(i.startswith("5.1") for i in items)


def test_a_gap_in_numbering_is_reported_by_stopping_at_the_gap():
    items = split_numbered("1. First one here.\n2. Second one here.\n4. Not the next number.")
    assert len(items) == 2 and "4. Not the next number." in items[1]


def test_age_range_reads_minimum_and_open_ended_maximum():
    assert age_range(split_numbered(INCLUSION)[0]) == (12.0, None)
    assert age_range("Aged 18 to 65 years inclusive.") == (18.0, 65.0)
    assert age_range("Participants must be at least 18 years of age.") == (18.0, None)
    assert age_range("No age is stated here.") == (None, None)


def test_extract_eligibility_from_windows_yields_clean_lists():
    inc = _doc(INCLUSION)
    exc = _doc("5.2. Exclusion Criteria\nParticipants are excluded if:\n"
               "1. Current need for hospitalization.\n2. Receiving dialysis.\n"
               "3. Known hypersensitivity to the study drug.")
    e = extract_eligibility(_doc("noise"), inclusion_doc=inc, exclusion_doc=exc)
    assert len(e.inclusion) == 3 and len(e.exclusion) == 3
    assert e.age_min == 12.0 and e.age_max is None
    assert e.exclusion[0].startswith("Current need for hospitalization")
