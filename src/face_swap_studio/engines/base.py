"""Face-swap engine adapter interface.

This product does NOT implement a new SOTA model. Engines wrap mature
open-source live pipelines (e.g. DeepFaceLive / InsightFace) behind a
stable API so the GUI and project layer stay engine-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import numpy as np


class EngineStatus(str, Enum):
    UNAVAILABLE = "unavailable"
    READY = "ready"
    RUNNING = "running"
    ERROR = "error"
    STUB = "stub"


@dataclass
class EngineCapabilities:
    name: str
    version: str
    supports_live_camera: bool
    supports_gpu: bool
    notes: str = ""
    is_stub: bool = True


@dataclass
class EngineFrame:
    """BGR uint8 frame (H, W, 3) as returned by OpenCV-style pipelines."""

    image: np.ndarray
    fps: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineConfig:
    """Runtime config passed into the engine."""

    camera_index: int = 0
    width: int = 1280
    height: int = 720
    gpu_device: str = "cuda:0"
    source_face_paths: list[str] = field(default_factory=list)
    watermark_text: Optional[str] = "FaceSwap Studio · 授权预览"
    extra: dict[str, Any] = field(default_factory=dict)


class FaceSwapEngine(ABC):
    """Adapter contract for live face-swap backends."""

    @abstractmethod
    def capabilities(self) -> EngineCapabilities:
        ...

    @abstractmethod
    def status(self) -> EngineStatus:
        ...

    @abstractmethod
    def initialize(self, config: EngineConfig) -> None:
        """Load models / open camera. May raise if backend missing."""
        ...

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @abstractmethod
    def read_frame(self) -> Optional[EngineFrame]:
        """Return next preview frame, or None if not running / no frame."""
        ...

    @abstractmethod
    def set_source_faces(self, paths: list[str]) -> None:
        ...

    def shutdown(self) -> None:
        """Optional cleanup; default stops then no-op."""
        try:
            self.stop()
        except Exception:
            pass
