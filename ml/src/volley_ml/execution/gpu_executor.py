"""Fail-closed compute placement without implicit cloud spending."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class GpuDevice(BaseModel):
    name: str = Field(min_length=1)
    memory_gib: float = Field(gt=0)


class RuntimeProfile(BaseModel):
    torch_version: str | None = None
    torch_cuda_version: str | None = None
    cuda_available: bool = False
    cuda_devices: list[GpuDevice] = Field(default_factory=list)
    physical_devices: list[GpuDevice] = Field(default_factory=list)


class ExecutionRequirement(BaseModel):
    stage: str = Field(min_length=1)
    requires_cuda: bool
    cpu_smoke_allowed: bool = False
    minimum_vram_gib: float = Field(ge=0)
    # Free-text caveat surfaced verbatim in ExecutionDecision.reason when
    # present -- e.g. "this VRAM gate is a reasoned estimate, not yet
    # profiled with a real batch." Optional: most gates don't need one.
    note: str | None = None


class ExecutionDecision(BaseModel):
    stage: str
    placement: Literal["local_cuda", "local_cpu_smoke", "external_gpu_required"]
    executable_now: bool
    reason: str


def decide_local_execution(
    profile: RuntimeProfile,
    requirement: ExecutionRequirement,
) -> ExecutionDecision:
    eligible_cuda = [
        device
        for device in profile.cuda_devices
        if device.memory_gib >= requirement.minimum_vram_gib
    ]
    note_suffix = f" ({requirement.note})" if requirement.note else ""
    if profile.cuda_available and eligible_cuda:
        device = max(eligible_cuda, key=lambda item: item.memory_gib)
        return ExecutionDecision(
            stage=requirement.stage,
            placement="local_cuda",
            executable_now=True,
            reason=f"{device.name} exposes {device.memory_gib:g} GiB to PyTorch{note_suffix}",
        )

    if not requirement.requires_cuda and requirement.cpu_smoke_allowed:
        return ExecutionDecision(
            stage=requirement.stage,
            placement="local_cpu_smoke",
            executable_now=True,
            reason="CPU execution is allowed only for integration smoke inference",
        )

    physical_note = ""
    if profile.physical_devices and not profile.cuda_available:
        best = max(profile.physical_devices, key=lambda item: item.memory_gib)
        physical_note = (
            f" A physical {best.name} ({best.memory_gib:g} GiB) exists, "
            "but the installed PyTorch runtime cannot access CUDA."
        )
    elif profile.cuda_devices:
        best = max(profile.cuda_devices, key=lambda item: item.memory_gib)
        physical_note = (
            f" Best CUDA device has {best.memory_gib:g} GiB; "
            f"the scheduling gate requires {requirement.minimum_vram_gib:g} GiB."
        )
    return ExecutionDecision(
        stage=requirement.stage,
        placement="external_gpu_required",
        executable_now=False,
        reason="The professional stage does not satisfy its local CUDA gate." + physical_note,
    )


def _physical_nvidia_devices() -> list[GpuDevice]:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []

    devices = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        name, memory_mib = (part.strip() for part in line.rsplit(",", maxsplit=1))
        devices.append(GpuDevice(name=name, memory_gib=round(float(memory_mib) / 1024, 3)))
    return devices


def probe_runtime() -> RuntimeProfile:
    physical_devices = _physical_nvidia_devices()
    try:
        import torch
    except ImportError:
        return RuntimeProfile(physical_devices=physical_devices)

    cuda_available = torch.cuda.is_available()
    cuda_devices = []
    if cuda_available:
        for index in range(torch.cuda.device_count()):
            properties = torch.cuda.get_device_properties(index)
            cuda_devices.append(
                GpuDevice(
                    name=properties.name,
                    memory_gib=round(properties.total_memory / (1024**3), 3),
                )
            )
    return RuntimeProfile(
        torch_version=torch.__version__,
        torch_cuda_version=torch.version.cuda,
        cuda_available=cuda_available,
        cuda_devices=cuda_devices,
        physical_devices=physical_devices,
    )


class ExternalGpuAuthorizationRequired(RuntimeError):
    pass


class ExternalGpuNotConfigured(RuntimeError):
    pass


class RunPodExecutor:
    """Deliberately non-submitting stub until credentials and spend are authorized."""

    def __init__(self, *, api_token: str | None, spend_authorized: bool = False) -> None:
        self.api_token = api_token
        self.spend_authorized = spend_authorized

    def submit(self, *, stage: str, idempotency_key: str) -> None:
        if not self.api_token:
            raise ExternalGpuNotConfigured("RunPod API token is not configured")
        if not self.spend_authorized:
            raise ExternalGpuAuthorizationRequired(
                f"external GPU spend is not authorized for {stage} ({idempotency_key})"
            )
        raise ExternalGpuNotConfigured(
            "RunPod submission remains intentionally unwired until a costed executor ADR "
            "is approved"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, required=True)
    args = parser.parse_args(argv)
    requirements = [
        ExecutionRequirement.model_validate(item)
        for item in json.loads(args.requirements.read_text(encoding="utf-8"))["stages"]
    ]
    profile = probe_runtime()
    output = {
        "runtime": profile.model_dump(),
        "decisions": [
            decide_local_execution(profile, requirement).model_dump()
            for requirement in requirements
        ],
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
