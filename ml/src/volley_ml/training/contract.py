"""Fail-closed experiment and metric gates for every perception stage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MetricGate(BaseModel):
    name: str = Field(min_length=1)
    direction: Literal["min", "max"]
    threshold: float
    unit: str = Field(min_length=1)
    slice: str = "overall"

    def passes(self, value: float) -> bool:
        return value >= self.threshold if self.direction == "min" else value <= self.threshold


class TrainingStage(BaseModel):
    name: str = Field(min_length=1)
    enabled: bool = True
    model_family: str = Field(min_length=1)
    model_variant: str = Field(min_length=1)
    input_specification: str = Field(min_length=1)
    pretrained_weights_license: str = Field(min_length=1)
    required_readiness: list[str] = Field(min_length=1)
    metric_gates: list[MetricGate] = Field(min_length=1)

    @model_validator(mode="after")
    def _metric_names_are_unique_per_slice(self) -> TrainingStage:
        keys = [(gate.name, gate.slice) for gate in self.metric_gates]
        if len(keys) != len(set(keys)):
            raise ValueError("metric gate names/slices must be unique within a stage")
        return self


class ExperimentContract(BaseModel):
    contract_version: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    split_manifest: str = Field(min_length=1)
    code_commit_required: bool = True
    seeds: list[int] = Field(min_length=3)
    stages: list[TrainingStage] = Field(min_length=1)

    @model_validator(mode="after")
    def _stage_names_are_unique(self) -> ExperimentContract:
        names = [stage.name for stage in self.stages]
        if len(names) != len(set(names)):
            raise ValueError("training stage names must be unique")
        if len(self.seeds) != len(set(self.seeds)):
            raise ValueError("experiment seeds must be unique")
        return self


class TrainingBlockedError(RuntimeError):
    pass


def load_experiment_contract(path: Path) -> ExperimentContract:
    return ExperimentContract.model_validate_json(path.read_text(encoding="utf-8"))


def assert_training_ready(
    contract: ExperimentContract,
    readiness_report: dict,
    *,
    stage_names: set[str] | None = None,
) -> None:
    report_version = readiness_report.get("dataset_version")
    if report_version != contract.dataset_version:
        raise TrainingBlockedError(
            f"readiness dataset {report_version!r} does not match {contract.dataset_version!r}"
        )
    readiness = readiness_report.get("readiness", {})
    blocked: list[str] = []
    for stage in contract.stages:
        if not stage.enabled or (stage_names is not None and stage.name not in stage_names):
            continue
        missing = [key for key in stage.required_readiness if readiness.get(key) is not True]
        if missing:
            blocked.append(f"{stage.name}: {', '.join(missing)}")
    if blocked:
        raise TrainingBlockedError("training readiness gate failed: " + "; ".join(blocked))


def evaluate_stage_metrics(stage: TrainingStage, metrics: dict[str, float]) -> list[str]:
    failures: list[str] = []
    for gate in stage.metric_gates:
        key = gate.name if gate.slice == "overall" else f"{gate.name}@{gate.slice}"
        if key not in metrics:
            failures.append(f"missing metric {key}")
            continue
        value = metrics[key]
        if not gate.passes(value):
            operator = ">=" if gate.direction == "min" else "<="
            failures.append(
                f"{key}={value:g} does not satisfy {operator}{gate.threshold:g} {gate.unit}"
            )
    return failures


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--stage", action="append", dest="stages")
    args = parser.parse_args(argv)

    contract = load_experiment_contract(args.contract)
    readiness = json.loads(args.readiness.read_text(encoding="utf-8"))
    assert_training_ready(
        contract,
        readiness,
        stage_names=set(args.stages) if args.stages else None,
    )
    print("Training readiness gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
