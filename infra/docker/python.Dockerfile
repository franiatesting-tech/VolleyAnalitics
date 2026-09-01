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
COPY packages/storage-py packages/storage-py
COPY services/api services/api
COPY services/worker services/worker

RUN uv sync --all-packages --no-dev --frozen

ENV PATH="/workspace/.venv/bin:$PATH"

# -----------------------------------------------------------------------
FROM deps AS api

WORKDIR /workspace/services/api
EXPOSE 8000
CMD ["uvicorn", "volley_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# -----------------------------------------------------------------------
FROM deps AS worker

# The worker is the only process that shells out to ffmpeg/ffprobe (video
# ingest -- services/worker/src/volley_worker/ingest.py). Install the
# pinned LGPL-only, dynamically-linked build per
# docs/licensing/LICENSE_DECISIONS.md D-006 -- never the distro package
# (verified during this phase: python:3.11-slim's own `apt-get install
# ffmpeg` resolves to a GPL build with libx264/libx265 enabled). Kept out
# of the shared `deps` layer above so the api image, which never touches
# video bytes, doesn't carry ffmpeg's ~55MB shared libs for no reason.
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends curl xz-utils ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY infra/scripts/install-ffmpeg-lgpl.sh /tmp/install-ffmpeg-lgpl.sh
RUN bash /tmp/install-ffmpeg-lgpl.sh && rm /tmp/install-ffmpeg-lgpl.sh
# Re-verify inside the image at build time too, not just trust the script's
# own internal checksum check -- fails the Docker build itself (not just a
# later runtime surprise) if this image ever ends up with a non-compliant
# ffmpeg on PATH.
RUN python -c "\
import sys; sys.path.insert(0, 'services/worker/src'); \
from volley_worker.ffprobe import verify_ffmpeg_build_is_license_clean; \
verify_ffmpeg_build_is_license_clean(); \
print('ffmpeg build verified license-clean per D-006')"

WORKDIR /workspace/services/worker
CMD ["celery", "-A", "volley_worker.celery_app.celery_app", "worker", "--loglevel=info"]
