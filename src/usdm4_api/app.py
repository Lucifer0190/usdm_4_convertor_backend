"""FastAPI service: upload a protocol PDF, receive its USDM 4.0 JSON.

    POST /v1/convert            multipart form, field ``file`` (a PDF)  ->  USDM JSON
    POST /v1/convert?include_report=true                                ->  {"usdm": ..., "report": ...}
    GET  /health, GET /v1/version

Configuration (environment variables):

    USDM4_API_KEYS        comma-separated keys; when set, requests need ``X-API-Key``.
                          When unset the service is open (logged at startup) - do not expose it.
    USDM4_MAX_UPLOAD_MB   default 60
    USDM4_MAX_CONCURRENT  conversions run at once, default 2 (others wait)
    USDM4_TIMEOUT_S       per-request limit, default 900

The conversion is synchronous: the request returns when the document is ready. A large
protocol with the LLM readers on can take minutes, so put a matching timeout on any proxy.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from usdm4_api.converter import ConversionError, Converter, CoreConverter

log = logging.getLogger("usdm4_api")
_CHUNK = 1024 * 1024


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def create_app(converter: Converter | None = None) -> FastAPI:
    """Build the app around ``converter`` (default: the ``usdm4_assure`` core)."""
    conv: Converter = converter or CoreConverter()
    keys = [k.strip() for k in os.environ.get("USDM4_API_KEYS", "").split(",") if k.strip()]
    max_bytes = _int_env("USDM4_MAX_UPLOAD_MB", 60) * 1024 * 1024
    timeout_s = _int_env("USDM4_TIMEOUT_S", 900)
    gate = asyncio.Semaphore(max(1, _int_env("USDM4_MAX_CONCURRENT", 2)))
    if not keys:
        log.warning("USDM4_API_KEYS is not set: the API is open. Do not expose it publicly.")

    app = FastAPI(title="USDM4 conversion API", version="0.1.0")

    def require_key(x_api_key: str | None = Header(default=None)) -> None:
        if not keys:
            return
        if x_api_key is None or not any(hmac.compare_digest(x_api_key, k) for k in keys):
            raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key.")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "converter": conv.name}

    @app.get("/v1/version")
    def version() -> dict:
        return {"api": app.version, "converter": conv.name}

    @app.post("/v1/convert", dependencies=[Depends(require_key)])
    async def convert(file: UploadFile = File(...), include_report: bool = False):
        with tempfile.TemporaryDirectory(prefix="usdm4-") as tmp:
            work = Path(tmp)
            pdf = work / "protocol.pdf"
            size = 0
            with pdf.open("wb") as out:
                while chunk := await file.read(_CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(status_code=413,
                                            detail=f"Upload exceeds {max_bytes // (1024 * 1024)} MB.")
                    out.write(chunk)
            if size == 0:
                raise HTTPException(status_code=400, detail="The upload is empty.")
            with pdf.open("rb") as fh:
                if fh.read(5) != b"%PDF-":
                    raise HTTPException(status_code=400, detail="The upload is not a PDF file.")
            try:
                async with gate:
                    result = await asyncio.wait_for(
                        run_in_threadpool(conv.convert, pdf, work / "out"), timeout=timeout_s)
            except TimeoutError:
                raise HTTPException(status_code=504,
                                    detail=f"Conversion exceeded {timeout_s} s.") from None
            except ConversionError as exc:
                return JSONResponse(status_code=422,
                                    content={"detail": str(exc), **exc.details})
        body = {"usdm": result.usdm, "report": result.report} if include_report else result.usdm
        return JSONResponse(content=body, headers={"X-Converter": conv.name})

    return app


def app_factory() -> FastAPI:
    """Run with ``uvicorn usdm4_api.app:app_factory --factory``."""
    return create_app()
