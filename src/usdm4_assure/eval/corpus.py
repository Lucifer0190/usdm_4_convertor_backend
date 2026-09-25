"""usdm_data protocol-PDF loader (task 3.7, DEVPLAN.md §3-C).

``spikes/_work/usdm_data`` (gitignored; ``git clone --depth 1
https://github.com/data4knowledge/usdm_data.git spikes/_work/usdm_data``) ships
one directory per study under ``source_data/protocols/``, holding the source
protocol PDF alongside its derivatives (a pre-assembled USDM JSON, sometimes an
extracted SoA or CRF PDF). The source protocol is always named exactly after
its directory — that convention, not a content sniff, is what tells it apart
from ``<dir>_USDM.pdf`` / ``<dir>_CRF.pdf`` / ``<dir>_SoA.pdf``.

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


def studies(root: Path = CORPUS_ROOT) -> list[Study]:
    """Every study under ``root`` whose source PDF is present.

    Returns ``[]`` (not an error) when ``root`` does not exist, so callers can
    skip cleanly rather than branch on :func:`available` separately.
    """
    if not root.is_dir():
        return []
    out = []
    for study_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        pdf = study_dir / f"{study_dir.name}.pdf"
        if pdf.is_file():
            out.append(Study(study_id=study_dir.name, pdf_path=pdf))
    return out
