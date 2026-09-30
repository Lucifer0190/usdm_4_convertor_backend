"""FastAPI service: upload a protocol PDF, receive its USDM 4.0 JSON.

    POST /v1/convert            multipart form, field ``file`` (a PDF)  ->  USDM JSON
    POST /v1/convert?include_report=true                                ->  {"usdm": ..., "report": ...}
    POST /v1/jobs   (same upload)  -> 202 {"id"};  GET /v1/jobs/{id} -> status, then the result
    GET  /health, GET /v1/version

Configuration (environment variables):

    OPEN_ROUTER_KEY       the LLM pipeline is the default and is REQUIRED: without a key the
                          service answers 503 instead of returning a thin deterministic result.
    USDM4_ALLOW_NO_LLM    set to 1 to allow deterministic-only conversion (tests, offline use)
    USDM4_API_KEYS        comma-separated keys; when set, requests need ``X-API-Key``.
                          When unset the service is open (logged at startup) - do not expose it.
    USDM4_MAX_UPLOAD_MB   default 60
    USDM4_MAX_CONCURRENT  conversions run at once, default 2 (others wait)
    USDM4_TIMEOUT_S       per-conversion limit, default 900
    USDM4_JOB_TTL_S       how long a finished job's result is kept, default 3600
    USDM4_RUN_CORE        set to 1 to run the official CDISC CORE gate (result in the report;
                          never blocks; needs CDISC_LIBRARY_API_KEY, else reported skipped)

The conversion is synchronous: the request returns when the document is ready. A large
protocol with the LLM readers on can take minutes, so put a matching timeout on any proxy.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import tempfile
import time
import uuid
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
    allow_no_llm = bool(os.environ.get("USDM4_ALLOW_NO_LLM"))
    job_ttl_s = _int_env("USDM4_JOB_TTL_S", 3600)

    def llm_ready() -> bool:
        return bool(getattr(conv, "llm_ready", lambda: True)())

    if not allow_no_llm and not llm_ready():
        log.warning("The LLM pipeline is required but no OPEN_ROUTER_KEY is configured: "
                    "conversions will be refused with 503.")
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
        return {"status": "ok", "converter": conv.name, "llm": llm_ready()}

    @app.get("/v1/version")
    def version() -> dict:
        return {"api": app.version, "converter": conv.name}

    def _require_llm() -> None:
        if not allow_no_llm and not llm_ready():
            raise HTTPException(
                status_code=503,
                detail="The LLM pipeline is required but no OPEN_ROUTER_KEY is configured "
                       "(set it, or USDM4_ALLOW_NO_LLM=1 to allow deterministic-only conversion).")

    async def _save_upload(file: UploadFile, dest: Path) -> None:
        size = 0
        with dest.open("wb") as out:
            while chunk := await file.read(_CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413,
                                        detail=f"Upload exceeds {max_bytes // (1024 * 1024)} MB.")
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The upload is empty.")
        with dest.open("rb") as fh:
            if fh.read(5) != b"%PDF-":
                raise HTTPException(status_code=400, detail="The upload is not a PDF file.")

    async def _run(pdf: Path, work: Path):
        """One conversion under the concurrency gate and the timeout."""
        async with gate:
            return await asyncio.wait_for(
                run_in_threadpool(conv.convert, pdf, work / "out"), timeout=timeout_s)

    def _log(event: str, **fields) -> None:
        log.info("%s %s", event, " ".join(f"{k}={v}" for k, v in fields.items()))

    def _body(result, include_report: bool) -> dict:
        return {"usdm": result.usdm, "report": result.report} if include_report else result.usdm

    @app.post("/v1/convert", dependencies=[Depends(require_key)])
    async def convert(file: UploadFile = File(...),  # noqa: B008
                      include_report: bool = False):
        _require_llm()
        started = time.time()
        with tempfile.TemporaryDirectory(prefix="usdm4-") as tmp:
            work = Path(tmp)
            pdf = work / "protocol.pdf"
            await _save_upload(file, pdf)
            try:
                result = await _run(pdf, work)
            except TimeoutError:
                _log("convert.timeout", seconds=timeout_s)
                raise HTTPException(status_code=504,
                                    detail=f"Conversion exceeded {timeout_s} s.") from None
            except ConversionError as exc:
                _log("convert.refused", reason=exc.details.get("reason", "assembly"))
                return JSONResponse(status_code=422,
                                    content={"detail": str(exc), **exc.details})
        run_id = str(result.report.get("run_id", ""))
        _log("convert.ok", run_id=run_id, seconds=round(time.time() - started, 1),
             findings=result.report.get("findings"))
        return JSONResponse(content=_body(result, include_report),
                            headers={"X-Converter": conv.name, "X-Run-Id": run_id})

    # --- async jobs: submit, then poll; a long conversion never holds one HTTP request ---- #
    jobs: dict[str, dict] = {}
    tasks: set[asyncio.Task] = set()

    def _prune() -> None:
        cutoff = time.time() - job_ttl_s
        for jid in [j for j, v in jobs.items() if v["status"] in ("done", "failed")
                    and v["finished"] < cutoff]:
            del jobs[jid]

    async def _job(jid: str, tmp: tempfile.TemporaryDirectory, pdf: Path) -> None:
        job = jobs[jid]
        try:
            job["status"] = "running"
            result = await _run(pdf, Path(tmp.name))
            job.update(status="done", result=result)
            _log("job.done", job=jid, run_id=result.report.get("run_id"))
        except ConversionError as exc:
            job.update(status="failed", error={"detail": str(exc), **exc.details}, code=422)
            _log("job.refused", job=jid, reason=exc.details.get("reason", "assembly"))
        except TimeoutError:
            job.update(status="failed", error={"detail": f"Conversion exceeded {timeout_s} s."},
                       code=504)
        except Exception as exc:
            log.exception("job %s crashed", jid)
            job.update(status="failed", error={"detail": f"Internal error: {type(exc).__name__}"},
                       code=500)
        finally:
            job["finished"] = time.time()
            tmp.cleanup()

    @app.post("/v1/jobs", status_code=202, dependencies=[Depends(require_key)])
    async def submit(file: UploadFile = File(...)):  # noqa: B008
        _require_llm()
        _prune()
        tmp = tempfile.TemporaryDirectory(prefix="usdm4-job-")
        pdf = Path(tmp.name) / "protocol.pdf"
        try:
            await _save_upload(file, pdf)
        except HTTPException:
            tmp.cleanup()
            raise
        jid = uuid.uuid4().hex
        jobs[jid] = {"status": "queued", "created": time.time(), "finished": 0.0}
        task = asyncio.create_task(_job(jid, tmp, pdf))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        _log("job.submitted", job=jid)
        return {"id": jid, "status": "queued", "poll": f"/v1/jobs/{jid}"}

    @app.get("/v1/jobs/{jid}", dependencies=[Depends(require_key)])
    async def job_status(jid: str, include_report: bool = False):
        job = jobs.get(jid)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown or expired job id.")
        out: dict = {"id": jid, "status": job["status"]}
        if job["status"] == "done":
            out["result"] = _body(job["result"], include_report)
            out["run_id"] = job["result"].report.get("run_id")
        elif job["status"] == "failed":
            out["error"] = job["error"]
            out["http_status"] = job["code"]
        return out

    return app


def app_factory() -> FastAPI:
    """Run with ``uvicorn usdm4_api.app:app_factory --factory``."""
    return create_app()
