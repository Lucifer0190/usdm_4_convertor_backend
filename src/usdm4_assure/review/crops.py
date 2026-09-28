"""Click-to-source crops — render the exact PDF region an ``AuditRecord``'s quote
came from (task 5.1). This is DESIGN.md L5's grounding made visible: a reviewer
sees the same rectangle our quote resolver computed, not a re-guess.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf

from usdm4_assure.contracts import BBox

# Points of context around the exact bbox, so a crop isn't a hairline sliver —
# and pixels-per-point, capped so a full-width table row doesn't render enormous.
PADDING_POINTS = 12.0
DPI = 200


def render_crop(pdf_path: str | Path, page: int, bbox: BBox, dpi: int = DPI) -> bytes:
    """PNG bytes of ``bbox`` (plus padding, clipped to the page) on 1-indexed ``page``.

    Raises:
        FileNotFoundError: ``pdf_path`` does not exist.
        ValueError: ``page`` is out of range for the document.
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"source PDF not found: {path}")
    with pymupdf.open(path) as doc:
        if not 1 <= page <= doc.page_count:
            raise ValueError(f"page {page} is out of range (document has {doc.page_count} pages)")
        pg = doc[page - 1]
        x0, y0, x1, y1 = bbox
        clip = pymupdf.Rect(x0 - PADDING_POINTS, y0 - PADDING_POINTS,
                            x1 + PADDING_POINTS, y1 + PADDING_POINTS) & pg.rect
        pix = pg.get_pixmap(dpi=dpi, clip=clip)
        return pix.tobytes("png")
