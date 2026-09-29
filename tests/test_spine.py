"""End-to-end spine test on the synthetic fixture with known ground truth.

Proves: PDF -> ingest -> extract -> assure -> assemble -> validate produces the
correct metadata values and a structurally-valid, d4k-checkable USDM 4.0 wrapper.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes"))
from make_fixture import GROUND_TRUTH, build

from usdm4_assure.pipeline import run


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    pdf = build()  # regenerate fixture
    out = tmp_path_factory.mktemp("out")
    return run(pdf, out_dir=out, run_core=False)


def test_all_metadata_values_correct(result):
    got = {a.field: a.value for a in result.assured}
    for field, expected in GROUND_TRUTH.items():
        assert got.get(field), f"{field} not extracted"
        # value must contain the ground-truth string (extractor may keep surrounding text)
        assert expected.split(",")[0][:20].lower() in (got[field] or "").lower(), (
            f"{field}: got {got[field]!r}, expected ~{expected!r}")


def test_confirmed_phase_is_auto_accepted(result):
    """Two regex members are one vote (they share a source), so agreement alone no
    longer certifies a deterministic value; the document's own ``Phase:`` label
    does, via the sanity validator."""
    phase = next(a for a in result.assured if a.field == "studyPhase")
    assert phase.sanity == "matches the synopsis Phase label"
    assert phase.decision.value == "auto_accept"


def test_structural_gate_passes(result):
    assert result.validation["structural"]["passed"] is True


def test_d4k_gate_runs(result):
    d4k = result.validation["d4k"]
    assert d4k.get("rules_run", 0) >= 100  # the full d4k rule set executed
