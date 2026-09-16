"""Validated local preferences. A saved mode is the only engine-selection authority."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

MODE_ENGINES = {"simple": "facefusion", "pro": "deepfacelive", "demo": "placeholder"}
DEFAULTS: dict[str, Any] = {
    "work_mode": "simple",
    "engine": "facefusion",
    "width": 1280,
    "height": 720,
    "camera_index": 0,
    "camera_name": "",
    "gpu_device": "cuda:0",
    "source_face_paths": [],
    "dfm_path": "",
    "facefusion_root": "",
    "facefusion_python": "",
    "deepfacelive_root": "",
    "userdata_dir": "",
    "facefusion_model": "inswapper_128",
    "facefusion_execution_provider": "cuda",
    "facefusion_startup_timeout": 90,
    "consent_acked": False,
    "watermark_enabled": True,
}


def normalize_preferences(raw: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULTS)
    for key, value in raw.items():
        if key in out:
            out[key] = value
    if out["work_mode"] not in MODE_ENGINES:
        out["work_mode"] = "simple"
    out["engine"] = MODE_ENGINES[out["work_mode"]]
    for key, lo, hi in (
        ("width", 320, 3840),
        ("height", 240, 2160),
        ("camera_index", 0, 32),
        ("facefusion_startup_timeout", 10, 600),
    ):
        try:
            out[key] = max(lo, min(hi, int(out[key])))
        except (TypeError, ValueError, OverflowError):
            out[key] = DEFAULTS[key]
    if out["work_mode"] == "simple":
        out["width"] = min(out["width"], 1920)
        out["height"] = min(out["height"], 1080)
    for key in (
        "camera_name",
        "gpu_device",
        "dfm_path",
        "facefusion_root",
        "facefusion_python",
        "deepfacelive_root",
        "userdata_dir",
        "facefusion_model",
        "facefusion_execution_provider",
    ):
        out[key] = str(out[key]) if isinstance(out[key], str) else DEFAULTS[key]
    paths = out["source_face_paths"]
    out["source_face_paths"] = (
        [p for p in paths if isinstance(p, str)] if isinstance(paths, list) else []
    )
    out["consent_acked"] = out["consent_acked"] is True
    out["watermark_enabled"] = out["watermark_enabled"] is not False
    return out


class PreferencesStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.last_error: str | None = None

    def load(self) -> dict[str, Any]:
        self.last_error = None
        if not self.path.exists():
            return normalize_preferences({})
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise TypeError("设置格式无效")
            return normalize_preferences(raw)
        except (OSError, ValueError, TypeError) as exc:
            self.last_error = str(exc)
            return normalize_preferences({})

    def save(self, settings: Mapping[str, Any]) -> None:
        data = normalize_preferences(settings)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
