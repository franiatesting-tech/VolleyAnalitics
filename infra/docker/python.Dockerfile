# syntax=docker/dockerfile:1
#
# Multi-target Dockerfile for the Python side of the monorepo (services/api,
# services/worker). One shared dependency-install layer (the whole uv
# workspace is copied in and synced once) so api/worker images stay in sync
# on shared package versions -- then two thin runtime targets on top.
#
# Build with: docker build -f infra/docker/python.Dockerfile --target api .
#             docker build -f infra/docker/python.Dockerfile --target worker .

FROM python:3.11-slim AS deps

RUN pip install --no-cache-dir uv==0.12.7
WORKDIR /workspace

COPY pyproject.toml uv.lock* ./
COPY packages/domain-py packages/domain-py
COPY services/api services/api
COPY services/worker services/worker

RUN uv sync --all-packages --no-dev --frozen || uv sync --all-packages --no-dev

ENV PATH="/workspace/.venv/bin:$PATH"

# -----------------------------------------------------------------------
FROM deps AS api

WORKDIR /workspace/services/api
EXPOSE 8000
CMD ["uvicorn", "volley_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# -----------------------------------------------------------------------
FROM deps AS worker

WORKDIR /workspace/services/worker
CMD ["celery", "-A", "volley_worker.celery_app.celery_app", "worker", "--loglevel=info"]
