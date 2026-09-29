# USDM4-Assure app image — dockerized from day one so the local PoC deploys anywhere.
FROM python:3.12-slim

WORKDIR /app

# System deps for pymupdf / pdfplumber rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[api]"

ENTRYPOINT ["usdm4"]
CMD ["--help"]
