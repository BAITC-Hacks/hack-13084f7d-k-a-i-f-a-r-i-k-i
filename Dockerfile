# syntax=docker/dockerfile:1

# CLI and analysis runtime. The Streamlit service follows in T13/T15.
FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b AS system

COPY --from=ghcr.io/astral-sh/uv:0.9.5@sha256:f459f6f73a8c4ef5d69f4e6fbbdb8af751d6fa40ec34b39a1ab469acd6e289b7 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-kaz \
        tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 orgagent \
    && useradd --uid 10001 --gid orgagent --create-home orgagent \
    && mkdir -p /app/runs /app/.cache/llm /app/data \
    && chown -R orgagent:orgagent /app

FROM system AS dependencies

COPY --chown=orgagent:orgagent pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --extra pipeline --no-install-project

FROM dependencies AS base

COPY --chown=orgagent:orgagent README.md ./
COPY --chown=orgagent:orgagent orgagent/ ./orgagent/
COPY --chown=orgagent:orgagent config/ ./config/
RUN uv sync --locked --no-dev --extra pipeline --no-editable

FROM dependencies AS dev-dependencies

# Visual DOCX QA is a development tool; it is not needed to generate reports.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends --yes \
        libreoffice-writer \
        poppler-utils \
        fonts-liberation \
        fonts-crosextra-carlito \
        fonts-crosextra-caladea \
    && rm -rf /var/lib/apt/lists/*

RUN uv sync --locked --no-dev --extra pipeline --extra dev --no-install-project

FROM dev-dependencies AS dev

COPY --chown=orgagent:orgagent README.md ./
COPY --chown=orgagent:orgagent orgagent/ ./orgagent/
COPY --chown=orgagent:orgagent config/ ./config/
RUN uv sync --locked --no-dev --extra pipeline --extra dev --no-editable
COPY --chown=orgagent:orgagent .env.example ./
COPY --chown=orgagent:orgagent tests/ ./tests/
COPY --chown=orgagent:orgagent eval/ ./eval/
COPY --chown=orgagent:orgagent ui/ ./ui/
COPY --chown=orgagent:orgagent api/ ./api/
COPY --chown=orgagent:orgagent data/demo/ ./data/demo/
COPY --chown=orgagent:orgagent HackAlem_test_dataset/ ./HackAlem_test_dataset/

USER orgagent
CMD ["sh", "-c", "pytest -q && ruff check . && ruff format --check ."]

FROM base AS runtime

USER orgagent
CMD ["orgagent", "check"]
