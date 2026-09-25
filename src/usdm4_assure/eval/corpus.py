"""usdm_data protocol-PDF loader (task 3.7, DEVPLAN.md §3-C).

``spikes/_work/usdm_data`` (gitignored; ``git clone --depth 1
https://github.com/data4knowledge/usdm_data.git spikes/_work/usdm_data``) ships
one directory per study under ``source_data/protocols/``, holding the source
protocol PDF alongside its derivatives (a pre-assembled USDM JSON, sometimes an
extracted SoA or CRF PDF). Usually the source protocol is named exactly after
its directory; that convention, not a content sniff, is what tells it apart
from ``<dir>_USDM.pdf`` / ``<dir>_CRF.pdf`` / ``<dir>_SoA.pdf``. One directory
(``CDISC_Pilot``) breaks the convention (``CDISC_Pilot_Study.pdf``), so a
directory with no exact match falls back to its one non-derivative PDF, if
there is exactly one — ambiguous directories (zero or several candidates) are
skipped, the same as a directory with no PDF at all.

This loader is a document source only. It does not read the corpus's own USDM
JSON as ground truth — Phase 3's eval (:mod:`usdm4_assure.eval.run`) compares
routing on vs. off against each other, not against a label; frozen per-field
labels are Phase 4's job (task 4.1).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS_ROOT = REPO_ROOT / "spikes" / "_work" / "usdm_data" / "source_data" / "protocols"


@dataclass(frozen=True)
class Study:
    """One usdm_data protocol: its id (directory name) and source PDF path."""
    study_id: str
    pdf_path: Path


def available() -> bool:
    """Whether the gitignored corpus has been cloned locally."""
    return CORPUS_ROOT.is_dir()


def _source_pdf(study_dir: Path) -> Path | None:
    """The one PDF in ``study_dir`` that every other PDF there is named *after*.

    Prefers an exact ``<dir>.pdf`` match. Otherwise: sort by stem length: if the
    shortest-stem PDF's stem is a prefix (on a ``_`` boundary) of every other
    PDF's stem — ``CDISC_Pilot_Study.pdf`` vs. ``CDISC_Pilot_Study_CRF.pdf`` —
    it is the source and the rest are its derivatives, whatever their suffix
    is named. No PDFs, or PDFs that don't share that "extends a common base"
    shape, is an ambiguous directory: ``None``, not a guess.
    """
    exact = study_dir / f"{study_dir.name}.pdf"
    if exact.is_file():
        return exact
    pdfs = sorted(study_dir.glob("*.pdf"), key=lambda p: len(p.stem))
    if not pdfs:
        return None
    base = pdfs[0]
    if all(p == base or p.stem.startswith(base.stem + "_") for p in pdfs):
        return base
    return None


def studies(root: Path = CORPUS_ROOT) -> list[Study]:
    """Every study under ``root`` whose source PDF can be identified unambiguously.

    Returns ``[]`` (not an error) when ``root`` does not exist, so callers can
    skip cleanly rather than branch on :func:`available` separately.
    """
    if not root.is_dir():
        return []
    out = []
    for study_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        pdf = _source_pdf(study_dir)
        if pdf is not None:
            out.append(Study(study_id=study_dir.name, pdf_path=pdf))
    return out
