"""usdm_data corpus loader (task 3.7). Skipped when the gitignored corpus
(spikes/_work/usdm_data) is absent."""
from __future__ import annotations

from pathlib import Path

import pytest

from usdm4_assure.eval.corpus import CORPUS_ROOT, Study, available, studies


def test_missing_root_returns_empty_not_error(tmp_path):
    assert studies(tmp_path / "does_not_exist") == []


def test_derivative_pdfs_are_not_studies(tmp_path):
    d = tmp_path / "Sponsor_NCT123_Cond"
    d.mkdir()
    (d / f"{d.name}_USDM.pdf").write_bytes(b"%PDF-1.4")
    (d / f"{d.name}_CRF.pdf").write_bytes(b"%PDF-1.4")
    assert studies(tmp_path) == []


def test_source_pdf_matching_directory_name_is_found(tmp_path):
    d = tmp_path / "Sponsor_NCT123_Cond"
    d.mkdir()
    (d / f"{d.name}.pdf").write_bytes(b"%PDF-1.4")
    (d / f"{d.name}_USDM.pdf").write_bytes(b"%PDF-1.4")
    found = studies(tmp_path)
    assert found == [Study(study_id=d.name, pdf_path=d / f"{d.name}.pdf")]


def test_results_are_sorted_by_study_id(tmp_path):
    for name in ["Zeta_NCT2", "Alpha_NCT1"]:
        d = tmp_path / name
        d.mkdir()
        (d / f"{name}.pdf").write_bytes(b"%PDF-1.4")
    assert [s.study_id for s in studies(tmp_path)] == ["Alpha_NCT1", "Zeta_NCT2"]


def test_real_corpus_loader_finds_studies():
    if not available():
        pytest.skip("usdm_data corpus not present (spikes/_work is gitignored)")
    found = studies()
    assert len(found) >= 20
    assert all(isinstance(s.pdf_path, Path) and s.pdf_path.is_file() for s in found)
    assert CORPUS_ROOT.name == "protocols"
