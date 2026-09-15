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

    def configure(self, config: EngineConfig) -> None:
        self._cfg = config
        dfm = config.extra.get("dfm_path") or ""
        path = Path(dfm) if dfm else None
        if not path or not path.is_file() or path.suffix.lower() != ".dfm":
            self._status = EngineStatus.ERROR
            self._error = "顶级模式需要有效的 .dfm 文件路径"
            self._dfm = None
            return
        self._dfm = path
        dfl_root = config.extra.get("deepfacelive_root")
        if dfl_root and Path(dfl_root).exists():
            self._status = EngineStatus.READY
            self._error = None
        else:
            self._status = EngineStatus.STUB
            self._error = "已选定 .dfm，但未检测到 DeepFaceLive 安装目录（待 2 号联调）。"

    def start(self) -> None:
        if self._status not in (EngineStatus.READY, EngineStatus.RUNNING):
            raise RuntimeError(self._error or "DeepFaceLive 未就绪（仍为 stub）")
        self._status = EngineStatus.RUNNING

    def stop(self) -> None:
        if self._status == EngineStatus.RUNNING:
            self._status = EngineStatus.READY

    def grab(self) -> EngineFrame:
        raise RuntimeError(f"DeepFaceLive 真推理尚未接线。dfm={self._dfm}")

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
