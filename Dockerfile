# syntax=docker/dockerfile:1

# T1 foundation. The Streamlit runtime and OCR system packages follow in T15.
FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b AS base

COPY --from=ghcr.io/astral-sh/uv:0.9.5@sha256:f459f6f73a8c4ef5d69f4e6fbbdb8af751d6fa40ec34b39a1ab469acd6e289b7 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN groupadd --gid 10001 orgagent \
    && useradd --uid 10001 --gid orgagent --create-home orgagent \
    && mkdir -p /app/runs /app/.cache/llm /app/data \
    && chown -R orgagent:orgagent /app

COPY --chown=orgagent:orgagent pyproject.toml uv.lock README.md ./
COPY --chown=orgagent:orgagent orgagent/ ./orgagent/
COPY --chown=orgagent:orgagent config/ ./config/
RUN uv sync --locked --no-dev --no-editable

FROM base AS dev

RUN uv sync --locked --no-dev --extra dev --no-editable
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
