from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENVS_WHERE_LOCAL_STORAGE_IS_ALLOWED = {"development", "test"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    env: str = Field(default="development", alias="ENV")
    database_url: str = Field(alias="DATABASE_URL")
    valkey_url: str = Field(alias="VALKEY_URL")

    # --- Storage (StorageAdapter, mirrors services/api's own settings --
    # see docs/architecture/DATA_FLOW.md's upload lifecycle) ---
    storage_backend: str = Field(default="local", alias="STORAGE_BACKEND")
    local_storage_dir: str = Field(default="/tmp/volley-local-storage", alias="LOCAL_STORAGE_DIR")
    local_storage_base_url: str = Field(
        default="http://localhost:8000", alias="LOCAL_STORAGE_BASE_URL"
    )
    local_storage_signing_secret: str = Field(
        default="dev-only-insecure-signing-secret", alias="LOCAL_STORAGE_SIGNING_SECRET"
    )
    r2_account_id: str | None = Field(default=None, alias="R2_ACCOUNT_ID")
    r2_bucket: str | None = Field(default=None, alias="R2_BUCKET")
    r2_access_key_id: str | None = Field(default=None, alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str | None = Field(default=None, alias="R2_SECRET_ACCESS_KEY")

    # --- Exploratory detection pipeline (volley_worker.detection) ---
    # Points at the local-only RF-DETR inference server run manually on the
    # host from ml/'s own venv (volley_ml.detection.server) --
    # `host.docker.internal` is Docker Desktop's documented hostname for a
    # container to reach its host, resolvable with no extra network config
    # on Windows/Mac. See detection.py's module docstring for why torch
    # never enters this container's own image.
    detection_inference_url: str = Field(
        default="http://host.docker.internal:8500", alias="DETECTION_INFERENCE_URL"
    )
    # Raised 1.0 -> 5.0fps 2026-09-01, explicit user tradeoff: "sube la
    # cadencia de muestreo de la bola asumiendo el coste de tiempo extra" --
    # 1.0fps (200ms-1000ms between samples) was too sparse to resolve a real
    # spike's direction change at all, which needs samples on the order of
    # a few hundred milliseconds apart to have any chance of reconstructing
    # its actual path (see ball_trajectory.ts's docstring for how the
    # frontend uses this denser sampling). This is a real ~5x wall-clock
    # multiplier on CPU-only inference (RFDETR_NANO_SMOKE.md's measured
    # ~0.4-1.7s/frame applies per sampled frame regardless of fps) -- a
    # caller can still override per-request (TriggerDetectionRequest.
    # sample_fps) to go higher on a short, deliberately scoped window via
    # start_offset_seconds/max_duration_seconds rather than paying an even
    # larger multiplier across an entire match by default.
    detection_sample_fps: float = Field(default=5.0, alias="DETECTION_SAMPLE_FPS")
    detection_threshold: float = Field(default=0.35, alias="DETECTION_THRESHOLD")
    # Lower than detection_threshold on purpose -- a real volleyball in
    # flight is small, fast and often motion-blurred, genuinely harder for
    # a generic (non-volleyball-fine-tuned) COCO detector to be confident
    # about than a person is.
    detection_ball_threshold: float = Field(default=0.15, alias="DETECTION_BALL_THRESHOLD")
    # Direct response to real user feedback: far-side (upper-frame, near-net)
    # players are poorly detected on a standard elevated wide-angle
    # broadcast shot -- a single full-frame RF-DETR nano pass gives them too
    # few effective pixels. Adds one extra forward pass per sampled frame on
    # a cropped upper region (see ml/detection/tiling.py) -- a real ~1.8-2x
    # per-frame CPU cost, applied unconditionally to every sampled frame of
    # every run (a much larger total-wall-clock multiplier than
    # detection_sample_fps's own precedent, since that only compounds with
    # this one). On by default since the user explicitly asked for this
    # quality improvement; disable per-deployment if the cost isn't worth it.
    detection_far_tiling_enabled: bool = Field(default=True, alias="DETECTION_FAR_TILING_ENABLED")

    # Direct response to real user feedback: sampling needs to match real
    # ball speed/direction changes, citing a 120km/h (33.3 m/s) ball. At
    # detection_sample_fps=5.0 (0.2s/sample) the ball can travel ~6.7m
    # between two consecutive samples -- over a third of an 18m court --
    # structurally too sparse to resolve a fast attack's direction.
    # Sampling the *whole* video at a much higher fps is CPU-prohibitive and
    # mostly wasted on non-ball-motion dead time; instead, once the baseline
    # pass finds a real ball sighting, a short window around it is
    # re-extracted and re-inferred at detection_burst_fps (see
    # ball_filtering.compute_burst_windows and detection.py's burst phase).
    # Bounded by detection_burst_max_windows so a rally-dense video can't
    # balloon cost unboundedly: worst case is
    # max_windows * window_radius*2 * burst_fps extra frames, each costing
    # the same ~0.4-1.7s/frame as any other sampled frame. On by default --
    # direct response to the user's explicit cadence request.
    detection_burst_enabled: bool = Field(default=True, alias="DETECTION_BURST_ENABLED")
    detection_burst_fps: float = Field(default=20.0, alias="DETECTION_BURST_FPS")
    detection_burst_window_radius_seconds: float = Field(
        default=0.6, alias="DETECTION_BURST_WINDOW_RADIUS_SECONDS"
    )
    detection_burst_max_windows: int = Field(default=40, alias="DETECTION_BURST_MAX_WINDOWS")

    # --- FFmpeg build verification (D-006, see LICENSE_DECISIONS.md) ---
    # The worker is the only process that ever invokes ffmpeg/ffprobe --
    # skip the startup license-build check only in contexts that
    # deliberately don't have a real ffmpeg on PATH (this project's own
    # unit tests stub ffprobe rather than shelling out).
    skip_ffmpeg_license_check: bool = Field(default=False, alias="SKIP_FFMPEG_LICENSE_CHECK")

    @model_validator(mode="after")
    def _local_storage_cannot_reach_production(self) -> "Settings":
        # Mirrors services/api/src/volley_api/core/config.py's identical
        # guard -- see that module for the full rationale (an
        # unauthenticated, forgeable cross-tenant upload primitive,
        # demonstrated live by independent security review). The worker
        # doesn't itself serve the upload route, but it shares this same
        # settings shape and the same insecure hardcoded default, so it
        # gets the same fail-fast treatment for defense in depth.
        if self.env not in _ENVS_WHERE_LOCAL_STORAGE_IS_ALLOWED:
            if self.storage_backend == "local":
                raise ValueError(
                    f"STORAGE_BACKEND=local is not allowed when ENV={self.env!r} -- "
                    "production must use STORAGE_BACKEND=r2."
                )
            if self.local_storage_signing_secret == "dev-only-insecure-signing-secret":
                raise ValueError(
                    "LOCAL_STORAGE_SIGNING_SECRET must be set to a real secret when "
                    f"ENV={self.env!r} -- the default value is hardcoded in this "
                    "codebase's source and public git history."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
