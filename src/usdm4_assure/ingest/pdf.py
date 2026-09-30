"""Foundation A — PDF -> layout blocks + rendered page images (deterministic, cached).

No LLM here. Uses PyMuPDF for text-with-coordinates, page rendering, and
(:mod:`usdm4_assure.ingest.geometry`) char-level geometry for L5 grounding.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf  # PyMuPDF

from usdm4_assure.contracts import Block, CharSpan, Document
from usdm4_assure.ingest.geometry import page_geometry

# A page under this many characters is, for our purposes, blank — a stray character or
# two (a stamp, a page number) should not count as "this page has a text layer", but a
# real page, however terse (a title page, a section divider), always clears it: this is
# a detector for "no text layer at all" (a scan), not for "not enough prose".
_MIN_PAGE_TEXT_CHARS = 3
_SCANNED_PAGE_RATIO = 0.8   # this share of blank pages means "no OCR text layer" (task C-9)


class ScannedPDFError(RuntimeError):
    """Raised by :func:`ingest` when a PDF has (almost) no extractable text layer.

    Most likely a scan with no OCR run on it. Every reader in this project works from
    the text layer (grounding a value means finding its exact substring in it), so
    there is nothing safe to extract — better to refuse clearly here than to silently
    deliver an empty or near-empty study (PLAN.md task C-9: "converts or is refused
    cleanly"). Running OCR is a real dependency (Tesseract) this project does not carry
    yet; adding it is a decision for a future task, not silently bundled with this one.
    """

    def __init__(self, pdf_path: Path, blank_pages: int, total_pages: int) -> None:
        self.pdf_path = pdf_path
        self.blank_pages = blank_pages
        self.total_pages = total_pages
        super().__init__(
            f"{pdf_path}: {blank_pages} of {total_pages} pages have no extractable text "
            "layer. This looks like a scanned document without OCR; this project does "
            "not run OCR, so it cannot be converted.")


def _classify(text: str, size: float, page_median_size: float) -> str:
    """Cheap block-kind heuristic. Real system refines this; enough for the spine."""
    t = text.strip()
    if not t:
        return "prose"
    if size >= page_median_size * 1.25 and len(t) < 120:
        return "heading"
    if t[0] in "*†‡" or t.lower().startswith(("note:", "footnote")):
        return "footnote"
    return "prose"


def ingest(pdf_path: str | Path, image_dir: str | Path | None = None,
           render_pages: int = 3) -> Document:
    """Parse a protocol PDF into a :class:`~usdm4_assure.contracts.Document`.

    Deterministic and side-effect-free apart from optionally writing page images.
    No LLM is involved, so the result is safe to cache keyed on the file hash.

    Args:
        pdf_path: Path to the source protocol PDF.
        image_dir: Directory to write rendered page PNGs into. If ``None`` no
            images are rendered (the deterministic table extractors do not need
            them; the vision SoA member does).
        render_pages: Number of leading pages to rasterize when ``image_dir`` is
            set. Only the early pages (title, synopsis, first SoA) feed the vision
            paths, so rendering every page is wasteful.

    Returns:
        A ``Document`` holding positioned text blocks, the concatenated full
        text, and the paths of any rendered page images.
    """
    pdf_path = Path(pdf_path)
    doc = pymupdf.open(pdf_path)
    blocks: list[Block] = []
    full_parts: list[str] = []
    chars: dict[int, list[CharSpan]] = {}
    page_text_chars = [0] * doc.page_count

    for pno in range(doc.page_count):
        page = doc[pno]
        _, page_chars = page_geometry(page, pno + 1)
        chars[pno + 1] = page_chars
        data = page.get_text("dict")
        sizes = [
            span["size"]
            for blk in data.get("blocks", [])
            for line in blk.get("lines", [])
            for span in line.get("spans", [])
        ]
        median = sorted(sizes)[len(sizes) // 2] if sizes else 10.0

        for blk in data.get("blocks", []):
            lines = blk.get("lines", [])
            if not lines:
                continue
            text = " ".join(
                span["text"] for line in lines for span in line.get("spans", [])
            ).strip()
            if not text:
                continue
            max_size = max(
                (span["size"] for line in lines for span in line.get("spans", [])),
                default=median,
            )
            x0, y0, x1, y1 = blk["bbox"]
            blocks.append(Block(
                text=text, page=pno + 1, bbox=(x0, y0, x1, y1),
                kind=_classify(text, max_size, median),
            ))
            full_parts.append(text)
            page_text_chars[pno] += len(text)

    blank_pages = sum(1 for n in page_text_chars if n < _MIN_PAGE_TEXT_CHARS)
    total_pages = doc.page_count
    if total_pages and blank_pages / total_pages >= _SCANNED_PAGE_RATIO:
        doc.close()
        raise ScannedPDFError(pdf_path, blank_pages, total_pages)

    page_images: list[Path] = []
    if image_dir is not None:
        image_dir = Path(image_dir)
        image_dir.mkdir(parents=True, exist_ok=True)
        for pno in range(min(render_pages, doc.page_count)):
            pix = doc[pno].get_pixmap(dpi=150)
            out = image_dir / f"page_{pno + 1:03d}.png"
            pix.save(out)
            page_images.append(out)

    doc.close()
    return Document(
        source=pdf_path,
        blocks=blocks,
        full_text="\n".join(full_parts),
        page_images=page_images,
        chars=chars,
    )
