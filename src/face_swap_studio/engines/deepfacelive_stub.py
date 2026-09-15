"""DeepFaceLive integration stub — documents how the real adapter will plug in.

MVP status
----------
This module does **not** call DeepFaceLive. It documents the intended
integration path so GPU workstations (RTX 4080/4090) can wire the mature
open-source live pipeline without rewriting the GUI.

Intended integration (future work on GPU machine)
-------------------------------------------------
1. Install DeepFaceLive (or a maintained fork) in a dedicated conda/venv,
   with CUDA matching the driver on the crew PC.
2. Prefer a **subprocess / IPC** bridge rather than importing DFL into the
   same process as PySide6 (avoids Qt + CUDA / torch conflicts):
     - Studio writes a small JSON job file: camera index, model paths,
       source face ids, resolution, output shared-memory / named-pipe id.
     - A thin `dfl_worker.py` (living next to DFL) starts the live pipeline
       and streams BGR frames back via shared memory or localhost socket.
3. Alternative: InsightFace-based live demo as a second adapter implementing
   the same ``FaceSwapEngine`` interface.
4. Map Studio concepts:
     - Project ``assets/``  →  DFL source face / model slot
     - Settings GPU note     →  CUDA_VISIBLE_DEVICES / device index
     - Watermark             →  post-process overlay in Studio (keep even if
                                DFL has its own HUD)
5. Do not train new SOTA models in this product; wrap mature pipelines.

When the real adapter is ready, replace ``DeepFaceLiveStubEngine`` with a
class that implements initialize/start/stop/read_frame against the worker,
and register it in ``create_engine()``.
"""

from __future__ import annotations

from typing import Optional

from face_swap_studio.engines.base import (
    EngineCapabilities,
    EngineConfig,
    EngineFrame,
    EngineStatus,
    FaceSwapEngine,
)


class DeepFaceLiveStubEngine(FaceSwapEngine):
    """Documented stub: raises clear errors; no DeepFaceLive dependency."""

    INTEGRATION_NOTES = __doc__

    def __init__(self) -> None:
        self._status = EngineStatus.STUB
        self._config: Optional[EngineConfig] = None

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            name="DeepFaceLive",
            version="stub-0.1",
            supports_live_camera=True,
            supports_gpu=True,
            notes=(
                "未集成。请在 RTX 4080/4090 工作站按 deepfacelive_stub.py "
                "文档接入 DFL worker，再切换引擎。"
            ),
            is_stub=True,
        )

    def status(self) -> EngineStatus:
        return self._status

    def initialize(self, config: EngineConfig) -> None:
        self._config = config
        self._status = EngineStatus.UNAVAILABLE
        raise RuntimeError(
            "DeepFaceLive 尚未接入。当前请使用 Placeholder 引擎。"
            "集成步骤见 face_swap_studio.engines.deepfacelive_stub 模块文档。"
        )

    def start(self) -> None:
        raise RuntimeError("DeepFaceLive stub: start() 不可用")

    def stop(self) -> None:
        self._status = EngineStatus.STUB

    def read_frame(self) -> Optional[EngineFrame]:
        return None

    def set_source_faces(self, paths: list[str]) -> None:
        if self._config is not None:
            self._config.source_face_paths = list(paths)


def create_engine(name: str = "placeholder") -> FaceSwapEngine:
    """Factory used by the app. Default is placeholder until DFL lands."""
    key = (name or "placeholder").strip().lower()
    if key in ("deepfacelive", "dfl"):
        return DeepFaceLiveStubEngine()
    from face_swap_studio.engines.placeholder import PlaceholderEngine

    return PlaceholderEngine()
