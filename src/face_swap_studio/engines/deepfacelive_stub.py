"""DeepFaceLive adapter — PRO mode (load .dfm). Integration: 编程助手2号."""

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
from face_swap_studio.engines.placeholder import PlaceholderEngine


class DeepFaceLiveStubEngine(FaceSwapEngine):
    def __init__(self) -> None:
        self._cfg: Optional[EngineConfig] = None
        self._status = EngineStatus.STUB
        self._error: Optional[str] = None
        self._dfm: Optional[Path] = None
        self._running = False

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            name="deepfacelive",
            version="stub-0.1",
            supports_live_camera=True,
            supports_gpu=True,
            notes="顶级模式：导入与 DFL 版本匹配的 .dfm；优先 NVIDIA 构建。",
            is_stub=True,
        )

    def status(self) -> EngineStatus:
        return self._status

    def initialize(self, config: EngineConfig) -> None:
        self._cfg = config
        dfm = config.extra.get("dfm_path") or ""
        path = Path(dfm) if dfm else None
        if not path or not path.is_file() or path.suffix.lower() != ".dfm":
            self._status = EngineStatus.ERROR
            self._error = "顶级模式需要有效的 .dfm 文件路径"
            self._dfm = None
            raise RuntimeError("DeepFaceLive 尚未接入：缺少 .dfm")
        self._dfm = path
        dfl_root = config.extra.get("deepfacelive_root")
        if dfl_root and Path(dfl_root).exists():
            self._status = EngineStatus.READY
            self._error = None
        else:
            self._status = EngineStatus.STUB
            self._error = "DeepFaceLive 尚未接入（stub）"
            raise RuntimeError("DeepFaceLive 尚未接入")

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


def create_engine(kind: str = "placeholder") -> FaceSwapEngine:
    kind = (kind or "placeholder").lower()
    if kind in ("deepfacelive", "dfl", "pro"):
        return DeepFaceLiveStubEngine()
    if kind in ("facefusion", "ff", "simple"):
        from face_swap_studio.engines.facefusion_stub import create_facefusion_engine

        return create_facefusion_engine()
    return PlaceholderEngine()
