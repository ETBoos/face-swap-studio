"""Build EngineConfig from UI settings — preserves extra (dfm_path, etc.)."""

from __future__ import annotations

from typing import Any, Mapping, Optional

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
    # 即用 / Deep-Live-Cam. Empty strings are skipped by the builder.
    "deeplivecam_root",
    "dlc_root",
    "deeplivecam_python",
    "dlc_session",
    "preview_target",
    "target_image",
    "execution_provider",
    "frame_processors",
    "execution_threads",
    "dlc_many_faces",
    "dlc_mouth_mask",
    "dlc_max_memory",
    "preview_timeout_sec",
    "live_mirror",
    "dlc_lang",
)


def build_engine_config(
    settings: Mapping[str, Any],
    *,
    source_face_paths: Optional[list[str]] = None,
    watermark_text: Optional[str] = "FaceSwap Studio · 授权预览",
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
        source_face_paths=list(source_face_paths or settings.get("source_face_paths") or []),
        watermark_text=watermark_text,
        extra=extra,
    )
