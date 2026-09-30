# Conversion API

A thin HTTP service (`src/usdm4_api`) around a swappable converter. It knows one interface,
`Converter.convert(pdf_path, work_dir) -> ConversionResult`; everything that reads the
protocol lives behind it (today the `usdm4_assure` core via `CoreConverter`), so the
extraction "brain" can change without touching the service.

## Run

```bash
pip install -e ".[api]"
uvicorn usdm4_api.app:app_factory --factory --port 8080
# or: docker compose --profile api up api
```

## Call

```bash
curl -X POST http://localhost:8080/v1/convert -H "X-API-Key: <key>" \
     -F "file=@protocol.pdf" -o study.usdm.json

# with a quality summary next to the document
curl -X POST "http://localhost:8080/v1/convert?include_report=true" -F "file=@protocol.pdf"
```

| Status | Meaning |
|---|---|
| 200 | body is the USDM 4.0 JSON (or `{"usdm", "report"}` with `include_report=true`) |
| 400 | not a PDF, or empty |
| 401 | `USDM4_API_KEYS` is set and `X-API-Key` is missing or wrong |
| 503 | the LLM pipeline is required but no `OPEN_ROUTER_KEY` is configured |
| 413 | larger than `USDM4_MAX_UPLOAD_MB` |
| 422 | the core ran but could not assemble a USDM document (details in the body) |
| 504 | exceeded `USDM4_TIMEOUT_S` |

`GET /health` and `GET /v1/version` are open for probes.

## Configuration

| Variable | Default | |
|---|---|---|
| `USDM4_API_KEYS` | unset | comma-separated keys; unset means the API is **open** |
| `USDM4_MAX_UPLOAD_MB` | 60 | |
| `USDM4_MAX_CONCURRENT` | 2 | conversions at once; others wait |
| `USDM4_TIMEOUT_S` | 900 | per conversion |
| `USDM4_JOB_TTL_S` | 3600 | how long a finished job's result is kept |
| `USDM4_RUN_CORE` | unset | `1` runs the official CDISC CORE gate; its result is in the report and never blocks. Needs `CDISC_LIBRARY_API_KEY`, else it is reported as skipped |
| `OPEN_ROUTER_KEY` | unset | **required**: the LLM pipeline is the default; without it the API answers 503 |

## Async jobs (for long conversions)

A conversion with the LLM on takes minutes. Submit it and poll instead of holding one request:

```bash
curl -s -X POST http://localhost:8080/v1/jobs -H "X-API-Key: $KEY" -F file=@protocol.pdf
# 202 {"id": "3f2a...", "status": "queued", "poll": "/v1/jobs/3f2a..."}
curl -s http://localhost:8080/v1/jobs/3f2a... -H "X-API-Key: $KEY"
# {"id": "...", "status": "queued|running|done|failed", "result": {...USDM...}}
```

The upload is validated when it is submitted (400/413/503 come back immediately). A finished
job carries `result` (the USDM, or `{usdm, report}` with `?include_report=true`) or, if it
failed, `error` and `http_status` (the status a direct call would have returned). Jobs live
in memory for `USDM4_JOB_TTL_S`: restarting the service loses them, so use `/v1/convert`
where that matters, or run one instance.

## Errors a client can act on

`POST /v1/convert` and a failed job return a `reason` where the cause is the document:

| Status | `reason` | Meaning |
|---|---|---|
| 422 | `corrupt_pdf` | The file cannot be read, or has no readable pages |
| 422 | `encrypted_pdf` | Password-protected; upload an unencrypted copy |
| 422 | `scanned_pdf_no_ocr` | No text layer (a scan); this project does not run OCR |
| 422 | *(none)* | The protocol was read but could not be assembled; `assembler_errors` say why |

Every successful `/v1/convert` also returns `X-Run-Id`, the id of the audit-trail run under
`data/audit`. Each request writes one structured log line (`convert.ok run_id=... seconds=...`).

## Things to know before deploying

- `/v1/convert` is synchronous: match any proxy or load-balancer timeout to
  `USDM4_TIMEOUT_S`, or use `/v1/jobs`.
- **Persist `data/`.** The audit trail (`data/audit`) and the LLM cache (`data/cache/llm.sqlite`)
  live there; `docker-compose.yml` mounts `./data:/app/data`. Without a volume both are lost
  when the container is replaced, and every LLM call is paid for again. Back up `data/audit`
  (it is the Part 11 evidence); the cache can be rebuilt. Run one instance, or share the volume
  carefully: SQLite is not built for several writers on a network share.
- With the LLM on, protocol text is sent to OpenRouter and on to the model providers.
  Confirm that is permitted for the documents you send.
- The `usdm4` dependency is GPL-3.0 (see `docs/references.md`).
- The Docker image has not been built or run on Linux by this project yet (the build machine
  had no running Docker daemon): run `docker compose --profile api up --build` and convert
  the synthetic protocol before relying on it.
