"""The converter interface and the adapter for the current extraction core."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class ConversionError(Exception):
    """The converter ran but could not produce a USDM document.

    ``details`` carries whatever the core reported (findings, validation) so the caller
    can see why; it is returned to the client as-is.
    """

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


@dataclass
class ConversionResult:
    """A converted protocol.

    Attributes:
        usdm: The USDM 4.0 wrapper document (JSON-serialisable).
        report: A small quality summary (triage counts, validation, run id). Free-form:
            different converters may report different things.
    """
    usdm: dict
    report: dict = field(default_factory=dict)


class Converter(Protocol):
    """What the API needs from an extraction core, and nothing more."""

    name: str

    def convert(self, pdf_path: Path, work_dir: Path) -> ConversionResult:
        """Convert one protocol PDF. ``work_dir`` is a scratch directory the converter owns."""
        ...


class CoreConverter:
    """Adapter for ``usdm4_assure`` (the current extraction core).

    Imported lazily so that the API process starts (and its tests run) without loading
    the whole pipeline until a conversion is actually requested.
    """

    name = "usdm4-assure"

    def llm_ready(self) -> bool:
        """True when the LLM readers will run: a key is configured and the LLM is not disabled."""
        import os

        from usdm4_assure.llm.config import openrouter_key
        return bool(openrouter_key()) and not os.environ.get("USDM4_NO_LLM")

    def core_enabled(self) -> bool:
        """The official CDISC CORE gate runs when ``USDM4_RUN_CORE`` is set. Its result goes
        in the report and never blocks a response; without ``CDISC_LIBRARY_API_KEY`` the
        gate reports itself skipped (validate/gate.py)."""
        import os
        return os.environ.get("USDM4_RUN_CORE", "").lower() in ("1", "true", "yes")

    @staticmethod
    def _check_pdf(pdf_path: Path) -> None:
        """Refuse a PDF that cannot be read at all, with a reason a client can act on."""
        import pymupdf
        try:
            doc = pymupdf.open(str(pdf_path))
        except Exception as exc:
            raise ConversionError("The PDF is corrupt or unreadable.",
                                  {"reason": "corrupt_pdf", "error": str(exc)[:200]}) from exc
        try:
            if doc.needs_pass or doc.is_encrypted:
                raise ConversionError(
                    "The PDF is password-protected; upload an unencrypted copy.",
                    {"reason": "encrypted_pdf"})
            if doc.page_count == 0:
                raise ConversionError("The PDF has no readable pages (corrupt or empty).",
                                      {"reason": "corrupt_pdf"})
        finally:
            doc.close()

    def convert(self, pdf_path: Path, work_dir: Path) -> ConversionResult:
        from usdm4_assure.ingest.pdf import ScannedPDFError
        from usdm4_assure.pipeline import run_full

        self._check_pdf(pdf_path)
        try:
            result = run_full(pdf_path, out_dir=work_dir, run_core=self.core_enabled())
        except ScannedPDFError as exc:
            # Refused cleanly (PLAN.md task C-9), not a 500: no dependency this project
            # carries can read a scan with no text layer, so there is nothing to convert.
            raise ConversionError(str(exc), {"reason": "scanned_pdf_no_ocr"}) from exc
        wrapper = (result.study or {}).get("wrapper")
        review_path = work_dir / "review.json"
        review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
        report = {
            "llm": self.llm_ready(),
            "core_requested": self.core_enabled(),
            "run_id": result.run_id,
            "source_sha256": result.source_sha256,
            "decision_summary": review.get("decision_summary", {}),
            "validation": review.get("validation"),
            "findings": len(review.get("findings", [])),
        }
        if not wrapper:
            raise ConversionError(
                "The protocol could not be assembled into a USDM document.",
                {"assembler_errors": (result.study or {}).get("assembler_errors", []),
                 "report": report})
        # The assembled objects can hold UUIDs and dates; make the document plain JSON.
        return ConversionResult(json.loads(json.dumps(wrapper, default=str)), report)
