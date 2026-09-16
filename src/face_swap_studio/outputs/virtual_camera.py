"""A latest-frame output worker; inference and the UI never wait for the receiver."""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from enum import Enum

import numpy as np

from face_swap_studio.engines.base import EngineFrame
from face_swap_studio.outputs.unity_camera import UnityCamera


class OutputStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


class VirtualCameraOutput:
    """Explicit start; stale/unsafe frames become a neutral slate, never raw video.

    RUNNING means the publisher is available, not that a particular call app has
    received it. `receiver_connected` reports a shared-memory receiver handshake.
    A fresh frame resumes a safety pause. A user pause should stop sending frames
    until the user explicitly requests output again.
    """

    def __init__(self, *, camera_factory: Callable = UnityCamera, stale_timeout: float = 1.0):
        self._factory = camera_factory
        self._stale_timeout = stale_timeout
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = OutputStatus.STOPPED
        self._error = ""
        self._device = ""
        self._latest: np.ndarray | None = None
        self._received_at = 0.0
        self._shape = (0, 0, 3)
        self._receiver_connected = False

    @property
    def device(self) -> str:
        with self._lock:
            return self._device

    @property
    def receiver_connected(self) -> bool:
        with self._lock:
            return self._receiver_connected

    def status(self) -> OutputStatus:
        with self._lock:
            return self._status

    def last_error(self) -> str:
        with self._lock:
            return self._error

    def start(self, width: int, height: int, fps: float = 30.0) -> None:
        if not (1 <= width <= 3840 and 1 <= height <= 2160):
            raise ValueError("输出尺寸必须在 3840 × 2160 以内。")
        if not math.isfinite(fps) or not 1 <= fps <= 120:
            raise ValueError("输出帧率必须在 1–120 之间。")
        with self._lock:
            if self._thread and self._thread.is_alive():
                if self._stop_event.is_set():
                    raise RuntimeError("输出组件正在停止，请稍后重试。")
                if self._shape != (height, width, 3):
                    raise RuntimeError("请先停止输出，再更改画面尺寸。")
                if self._status == OutputStatus.PAUSED:
                    self._latest, self._received_at = None, 0.0
                    self._error = ""
                    self._status = OutputStatus.RUNNING
                return
            self._shape = (height, width, 3)
            self._status = OutputStatus.STARTING
            self._error, self._device = "", ""
            self._latest, self._received_at = None, 0.0
            self._receiver_connected = False
            self._stop_event = threading.Event()
            self._thread = threading.Thread(
                target=self._run, args=(width, height, fps, self._stop_event),
                name="virtual-camera-output", daemon=True,
            )
            self._thread.start()

    def send(self, frame: EngineFrame) -> bool:
        meta, pixels = frame.meta, frame.image
        if not (
            meta.get("stub") is False
            and meta.get("face_swapped") is True
            and meta.get("safe_to_output") is True
        ):
            self.pause("未收到可输出的换脸画面，已显示暂停画面。")
            return False
        with self._lock:
            if self._status not in (OutputStatus.STARTING, OutputStatus.RUNNING, OutputStatus.PAUSED):
                return False
            if not isinstance(pixels, np.ndarray) or pixels.dtype != np.uint8 or pixels.shape != self._shape:
                self.pause("画面尺寸或格式发生变化，请停止输出后重试。")
                return False
            self._latest = np.array(pixels, copy=True, order="C")
            self._received_at = time.monotonic()
            if self._status == OutputStatus.PAUSED:
                self._status = OutputStatus.RUNNING
            self._error = ""
            return True

    def pause(self, reason: str = "输出已暂停") -> None:
        with self._lock:
            if self._status in (OutputStatus.STOPPED, OutputStatus.ERROR):
                return
            self._latest = None
            self._received_at = 0.0
            self._error = reason
            self._status = OutputStatus.PAUSED

    def stop(self) -> None:
        with self._lock:
            self._latest = None
            self._stop_event.set()
            self._status = OutputStatus.STOPPED
            self._receiver_connected = False
        # Resource disposal runs in the worker; do not freeze the UI on drivers.

    def _run(self, width: int, height: int, fps: float, stop: threading.Event):
        camera = None
        slate = np.full((height, width, 3), (32, 28, 24), dtype=np.uint8)
        try:
            camera = self._factory(width=width, height=height, fps=fps)
            with self._lock:
                self._device = str(camera.device)
                if not stop.is_set() and self._status == OutputStatus.STARTING:
                    self._status = OutputStatus.RUNNING
            period = 1.0 / fps
            while not stop.is_set():
                started = time.monotonic()
                with self._lock:
                    stale = started - self._received_at > self._stale_timeout
                    pixels = self._latest
                    if pixels is None or stale or self._status == OutputStatus.PAUSED:
                        pixels = slate
                        if stale and self._latest is not None:
                            self._latest = None
                            self._status = OutputStatus.PAUSED
                            self._error = "换脸画面已中断，输出已切换为暂停画面。"
                connected = camera.send(pixels)
                with self._lock:
                    self._receiver_connected = connected is not False
                stop.wait(max(0, period - (time.monotonic() - started)))
        except Exception as exc:  # noqa: BLE001 — contain native driver failures
            with self._lock:
                if not stop.is_set():
                    self._status = OutputStatus.ERROR
                    self._error = f"无法启动或维持虚拟摄像头：{exc}"
        finally:
            if camera is not None:
                try:
                    camera.send(slate)
                except Exception:
                    logging.getLogger(__name__).debug("Final output slate failed", exc_info=True)
                try:
                    camera.close()
                except Exception:
                    logging.getLogger(__name__).debug("Output cleanup failed", exc_info=True)
            with self._lock:
                self._receiver_connected = False
                if stop.is_set():
                    self._status = OutputStatus.STOPPED
