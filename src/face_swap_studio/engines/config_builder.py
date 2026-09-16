"""Build EngineConfig from UI settings — preserves extra (dfm_path, etc.)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from face_swap_studio.engines.base import EngineConfig

# Keys that ride in EngineConfig.extra (must not be dropped).
EXTRA_SETTING_KEYS = (
    "dfm_path",
    "deepfacelive_root",
    "userdata_dir",
    "dfm_version_hint",
    "require_nvidia",
    "allow_unknown_build",
    "no_cuda",
    "facefusion_root",
    "facefusion_python",
    "facefusion_model",
    "facefusion_execution_provider",
    "facefusion_startup_timeout",
)


def build_engine_config(
    settings: Mapping[str, Any],
    *,
    source_face_paths: list[str] | None = None,
    watermark_text: str | None = "FaceSwap Studio · 授权预览",
) -> EngineConfig:
    """Map UI/settings dict → EngineConfig, keeping PRO fields in ``extra``."""
    extra: dict[str, Any] = {}
    # Prefer nested extra if present, then top-level keys.
    nested = settings.get("extra")
    if isinstance(nested, dict):
        extra.update(nested)
    for key in EXTRA_SETTING_KEYS:
        if key in settings and settings[key] not in (None, ""):
            extra[key] = settings[key]
    return EngineConfig(
        camera_index=int(settings.get("camera_index", 0)),
        width=int(settings.get("width", 1280)),
        height=int(settings.get("height", 720)),
        gpu_device=str(settings.get("gpu_device", "cuda:0")),
        source_face_paths=list(
            (settings.get("source_face_paths") or [])
            if source_face_paths is None else source_face_paths
        ),
        watermark_text=watermark_text,
        extra=extra,
    )
