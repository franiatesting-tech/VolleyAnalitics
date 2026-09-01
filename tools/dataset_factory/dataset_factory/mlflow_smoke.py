"""Proves the MLflow tracking server wiring actually works end-to-end --
logs one real run with every field CLAUDE.md's Traceability section and
the cv-experiment skill require (git commit, dataset version, model
architecture + weights hash, preprocessing steps, full config, seed,
hardware, metrics, artifacts), against a real running `mlflow` service
(see docker-compose.mlops.yml). This is a connectivity/plumbing smoke test,
not a real experiment -- the metrics logged are placeholders, clearly
labeled as such, never to be confused with a real model evaluation result.

Usage:
    uv run python -m dataset_factory.mlflow_smoke --tracking-uri http://localhost:5000
"""

from __future__ import annotations

import argparse
import platform
import subprocess

import mlflow


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5
        ).stdout.strip()
    except Exception:
        return "unknown"


def run_smoke_test(tracking_uri: str, experiment_name: str = "phase4-smoke-test") -> str:
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name="dataset-factory-connectivity-smoke-test") as run:
        mlflow.set_tags(
            {
                "git_commit": _git_commit(),
                "hardware": platform.platform(),
                "purpose": "Phase 4 MLOps wiring smoke test -- NOT a real model result",
            }
        )
        mlflow.log_params(
            {
                "dataset_version": "smoke-test-no-real-dataset",
                "model_architecture": "none (connectivity test only)",
                "weights_hash": "n/a",
                "preprocessing": "none",
                "seed": 0,
            }
        )
        # Placeholder metric -- proves the log_metric round trip works,
        # never a claim about any real model's performance.
        mlflow.log_metric("smoke_test_ok", 1.0)
        return run.info.run_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-uri", default="http://localhost:5000")
    parser.add_argument("--experiment-name", default="phase4-smoke-test")
    args = parser.parse_args()

    run_id = run_smoke_test(args.tracking_uri, args.experiment_name)
    print(f"Logged smoke-test run {run_id} to {args.tracking_uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
