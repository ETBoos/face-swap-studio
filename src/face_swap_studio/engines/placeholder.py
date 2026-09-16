"""Placeholder engine — camera or synthetic frame with banner overlay.

Used until DeepFaceLive / InsightFace is integrated on a GPU workstation.
Does NOT perform face swap.
"""

from __future__ import annotations

import time
import sys
from typing import Optional

import cv2
import numpy as np

from face_swap_studio.engines.base import (
    EngineCapabilities,
    EngineConfig,
    EngineFrame,
    EngineStatus,
    FaceSwapEngine,
)


class PlaceholderEngine(FaceSwapEngine):
    """Shows live camera (if available) or a generated slate; overlays stub notice."""

    def __init__(self) -> None:
        self._status = EngineStatus.STUB
        self._config: Optional[EngineConfig] = None
        self._cap: Optional[cv2.VideoCapture] = None
        self._running = False
        self._t0 = time.perf_counter()
        self._frame_i = 0

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            name="Placeholder",
            version="0.1.0",
            supports_live_camera=True,
            supports_gpu=False,
            notes="无真实换脸。仅摄像头/合成画面 + 水印占位。",
            is_stub=True,
        )

    def status(self) -> EngineStatus:
        return self._status

    def initialize(self, config: EngineConfig) -> None:
        self._config = config
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        self._cap = cv2.VideoCapture(config.camera_index, backend)
        if self._cap is not None and self._cap.isOpened():
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
        self._status = EngineStatus.READY

    def start(self) -> None:
        if self._status not in (EngineStatus.READY, EngineStatus.RUNNING, EngineStatus.STUB):
            self._status = EngineStatus.READY
        self._running = True
        self._status = EngineStatus.RUNNING
        self._t0 = time.perf_counter()
        self._frame_i = 0

    def stop(self) -> None:
        self._running = False
        if self._status == EngineStatus.RUNNING:
            self._status = EngineStatus.READY

    def set_source_faces(self, paths: list[str]) -> None:
        # Stub: record paths only; no model load.
        if self._config is not None:
            self._config.source_face_paths = list(paths)

    def read_frame(self) -> Optional[EngineFrame]:
        if not self._running or self._config is None:
            return None

        frame: Optional[np.ndarray] = None
        if self._cap is not None and self._cap.isOpened():
            ok, grabbed = self._cap.read()
            if ok and grabbed is not None:
                frame = grabbed

        if frame is None:
            frame = self._synthetic_slate()

        h, w = self._config.height, self._config.width
        if frame.shape[0] != h or frame.shape[1] != w:
            frame = cv2.resize(frame, (w, h))

        self._draw_overlays(frame)
        self._frame_i += 1
        elapsed = max(time.perf_counter() - self._t0, 1e-6)
        fps = self._frame_i / elapsed
        return EngineFrame(image=frame, fps=fps, meta={"engine": "placeholder", "stub": True})

    def shutdown(self) -> None:
        self.stop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._status = EngineStatus.STUB

    def _synthetic_slate(self) -> np.ndarray:
        assert self._config is not None
        h, w = self._config.height, self._config.width
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:] = (40, 40, 48)
        # Moving bar so preview looks "live"
        x = int((time.perf_counter() * 80) % max(w - 40, 1))
        cv2.rectangle(img, (x, h // 2 - 8), (x + 40, h // 2 + 8), (80, 160, 220), -1)
        return img

    def _draw_overlays(self, frame: np.ndarray) -> None:
        assert self._config is not None
        lines = [
            "FaceSwap Studio — STUB / 占位引擎",
            "尚未接入 DeepFaceLive，当前无真实换脸",
            "仅限授权影视用途",
        ]
        y = 36
        for line in lines:
            cv2.putText(
                frame,
                line,
                (24, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 220, 255),
                2,
                cv2.LINE_AA,
            )
            y += 32
        if self._config.watermark_text:
            cv2.putText(
                frame,
                self._config.watermark_text,
                (24, frame.shape[0] - 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (200, 200, 200),
                1,
                cv2.LINE_AA,
            )
