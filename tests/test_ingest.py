"""ingest(): a PDF with (almost) no extractable text layer is refused cleanly, not
silently converted into an empty study (PLAN.md task C-9)."""
from __future__ import annotations

import pymupdf
import pytest

from usdm4_assure.ingest.pdf import ScannedPDFError, ingest


def _pdf(tmp_path, name, pages_with_text):
    """``pages_with_text`` real text pages, then enough blank (image-only) pages that
    every page after it has nothing but a drawn rectangle — no text layer at all."""
    path = tmp_path / name
    doc = pymupdf.open()
    for i in range(pages_with_text):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Real protocol text on page {i + 1}.", fontsize=11)
    for _ in range(10 - pages_with_text):
        page = doc.new_page(width=612, height=792)
        page.draw_rect(pymupdf.Rect(50, 50, 550, 750), color=(0, 0, 0))   # a "scanned image"
    doc.save(str(path))
    doc.close()
    return path


def test_a_fully_scanned_pdf_is_refused(tmp_path):
    path = _pdf(tmp_path, "scan.pdf", pages_with_text=0)
    with pytest.raises(ScannedPDFError) as exc:
        ingest(path)
    assert exc.value.blank_pages == 10 and exc.value.total_pages == 10
    assert "no extractable text" in str(exc.value)


def test_a_mostly_scanned_pdf_with_one_text_page_is_still_refused(tmp_path):
    path = _pdf(tmp_path, "mostly_scan.pdf", pages_with_text=1)   # 9/10 blank >= 80%
    with pytest.raises(ScannedPDFError):
        ingest(path)


def test_a_born_digital_pdf_is_never_refused(tmp_path):
    path = _pdf(tmp_path, "digital.pdf", pages_with_text=10)
    doc = ingest(path)
    assert doc.blocks


def test_a_short_real_document_is_not_mistaken_for_a_scan(tmp_path):
    """A 1-2 page real document must not trip the ratio check just for being short."""
    path = tmp_path / "short.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "A short but genuine protocol page with real text.", fontsize=11)
    doc.save(str(path))
    doc.close()
    result = ingest(path)
    assert result.blocks
