# Minimal MLflow tracking server image. Deliberately NOT pulled from a
# third-party registry tag (e.g. ghcr.io/mlflow/mlflow) that this session
# couldn't independently verify the provenance/tag history of -- `pip
# install mlflow` pins the exact version the same way every other Python
# dependency in this repo does (uv.lock-equivalent: the version pin below),
# via the same PyPI trust boundary every other dependency in this project
# already goes through. See docs/licensing/OSS_MANIFEST.md -- MLflow is
# Apache-2.0, already cleared.
FROM python:3.11-slim

RUN pip install --no-cache-dir mlflow==3.15.2

EXPOSE 5000
# --backend-store-uri: SQLite file in the mounted volume (see
# docker-compose.mlops.yml) -- fine for local/dev experiment tracking; a
# real Postgres-backed store is a later, measured decision, not assumed
# here (see docs/datasets/README.md's "not yet decided" note).
# --artifact-root: local filesystem, also volume-mounted.
CMD ["mlflow", "server", \
     "--host", "0.0.0.0", "--port", "5000", \
     "--backend-store-uri", "sqlite:////mlflow-data/mlflow.db", \
     "--default-artifact-root", "/mlflow-data/artifacts"]
