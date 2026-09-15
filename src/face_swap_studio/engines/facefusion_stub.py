"""FaceFusion adapter — SIMPLE mode (easy config, no .dfm)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from face_swap_studio.engines.base import (
    EngineCapabilities,
    EngineConfig,
    EngineFrame,
    EngineStatus,
    FaceSwapEngine,
)


class FaceFusionStubEngine(FaceSwapEngine):
    def __init__(self, facefusion_root: Optional[Path] = None) -> None:
        self._root = Path(facefusion_root) if facefusion_root else None
        self._cfg: Optional[EngineConfig] = None
        self._status = EngineStatus.STUB
        self._error: Optional[str] = None
        self._running = False

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            name="facefusion",
            version="stub-0.1",
            supports_live_camera=True,
            supports_gpu=True,
            notes="简易模式：无需 .dfm；需本机安装 FaceFusion 后接线。",
            is_stub=True,
        )

    def status(self) -> EngineStatus:
        return self._status

    def initialize(self, config: EngineConfig) -> None:
        self._cfg = config
        faces = config.source_face_paths or []
        if not faces:
            self._status = EngineStatus.ERROR
            self._error = "简易模式需要至少一张目标脸图片"
            raise RuntimeError(self._error)
        root = config.extra.get("facefusion_root") or self._root
        if root and Path(root).exists():
            self._status = EngineStatus.READY
            self._error = None
        else:
            self._status = EngineStatus.STUB
            self._error = "FaceFusion 尚未接入（stub）。安装后填写 facefusion_root。"
            raise RuntimeError("FaceFusion 尚未接入")

    def start(self) -> None:
        self._running = True
        if self._status == EngineStatus.READY:
            self._status = EngineStatus.RUNNING

    def stop(self) -> None:
        self._running = False
        if self._status == EngineStatus.RUNNING:
            self._status = EngineStatus.READY

    def set_source_faces(self, paths: list[str]) -> None:
        if self._cfg is not None:
            self._cfg.source_face_paths = list(paths)

    def read_frame(self) -> Optional[EngineFrame]:
        return None

    def last_error(self) -> Optional[str]:
        return self._error


def create_facefusion_engine(root: Optional[str] = None) -> FaceSwapEngine:
    return FaceFusionStubEngine(Path(root) if root else None)
