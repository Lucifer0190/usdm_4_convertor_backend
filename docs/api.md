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
| `USDM4_TIMEOUT_S` | 900 | per request |
| `OPEN_ROUTER_KEY` | unset | **required**: the LLM pipeline is the default; without it the API answers 503 |

## Things to know before deploying

- The call is synchronous. Without the LLM a protocol takes about 15 s; with it, minutes.
  Match any proxy or load-balancer timeout to `USDM4_TIMEOUT_S`.
- The audit trail and LLM cache are SQLite files under `data/`; mount that volume, and use
  one instance (or shared storage) so they are not split.
- With the LLM on, protocol text is sent to OpenRouter and on to the model providers.
  Confirm that is permitted for the documents you send.
- The `usdm4` dependency is GPL-3.0 (see `docs/references.md`).
