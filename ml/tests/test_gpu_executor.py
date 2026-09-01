import pytest

from volley_ml.execution.gpu_executor import (
    ExecutionRequirement,
    ExternalGpuAuthorizationRequired,
    ExternalGpuNotConfigured,
    GpuDevice,
    RunPodExecutor,
    RuntimeProfile,
    decide_local_execution,
)


def test_cuda_stage_uses_eligible_local_device():
    profile = RuntimeProfile(
        torch_version="2.13",
        torch_cuda_version="13.0",
        cuda_available=True,
        cuda_devices=[GpuDevice(name="GPU", memory_gib=16)],
    )
    requirement = ExecutionRequirement(
        stage="player_detection_training",
        requires_cuda=True,
        minimum_vram_gib=12,
    )
    decision = decide_local_execution(profile, requirement)
    assert decision.executable_now
    assert decision.placement == "local_cuda"


def test_cpu_is_allowed_only_for_explicit_smoke_stage():
    profile = RuntimeProfile(cuda_available=False)
    requirement = ExecutionRequirement(
        stage="rfdetr_nano_smoke",
        requires_cuda=False,
        cpu_smoke_allowed=True,
        minimum_vram_gib=0,
    )
    decision = decide_local_execution(profile, requirement)
    assert decision.executable_now
    assert decision.placement == "local_cpu_smoke"


def test_physical_gpu_without_cuda_runtime_does_not_pass_gate():
    profile = RuntimeProfile(
        torch_version="2.13.0+cpu",
        cuda_available=False,
        physical_devices=[GpuDevice(name="GTX 1650", memory_gib=4)],
    )
    requirement = ExecutionRequirement(
        stage="pose_training",
        requires_cuda=True,
        minimum_vram_gib=16,
    )
    decision = decide_local_execution(profile, requirement)
    assert not decision.executable_now
    assert decision.placement == "external_gpu_required"
    assert "cannot access CUDA" in decision.reason


def test_nano_training_gate_fits_a_local_4gib_card_once_cuda_is_available():
    """The exact scenario this stage exists for: a GTX 1650 4 GiB (this
    project's own reference local machine, see PROJECT_STATUS.md) with a
    CUDA-enabled PyTorch installed must pass the nano-specific gate that
    the full-size player_detection_training stage (12 GiB) never would."""
    profile = RuntimeProfile(
        torch_version="2.13.0",
        torch_cuda_version="12.4",
        cuda_available=True,
        cuda_devices=[GpuDevice(name="NVIDIA GeForce GTX 1650", memory_gib=4.0)],
    )
    requirement = ExecutionRequirement(
        stage="player_detection_training_nano",
        requires_cuda=True,
        minimum_vram_gib=4,
        note="ESTIMATE, not yet profiled with a real batch",
    )
    decision = decide_local_execution(profile, requirement)
    assert decision.executable_now
    assert decision.placement == "local_cuda"
    assert "ESTIMATE" in decision.reason


def test_runpod_stub_requires_configuration_and_spend_authorization():
    with pytest.raises(ExternalGpuNotConfigured, match="token"):
        RunPodExecutor(api_token=None).submit(stage="train", idempotency_key="job-1")
    with pytest.raises(ExternalGpuAuthorizationRequired, match="not authorized"):
        RunPodExecutor(api_token="secret", spend_authorized=False).submit(
            stage="train", idempotency_key="job-1"
        )
