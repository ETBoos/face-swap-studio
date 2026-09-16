"""Windows sender for our separately installed MIT UnityCapture-derived filter.

Protocol reference: native/virtual_camera/shared.inl; see its LICENSE.txt.
No DLL is registered or downloaded by this module.
"""

from __future__ import annotations

import ctypes
import struct
import sys
import time

import numpy as np

SERVICE_CLSID = "{E3B79076-C56E-4E15-95B9-4B6F523A0010}"
DEVICE_NAME = "FaceSwap Studio Camera"
MAX_IMAGE_BYTES = 3840 * 2160 * 8
HEADER_SIZE = 32


def encode_rgba(image: np.ndarray) -> np.ndarray:
    """Convert top-down BGR to the filter's bottom-up RGBA DIB row order."""
    rgba = np.empty((*image.shape[:2], 4), dtype=np.uint8)
    rgba[:, :, :3] = image[::-1, :, ::-1]
    rgba[:, :, 3] = 255
    return rgba


class UnityCamera:
    """Nonblocking send to camera zero. False means no consumer has opened it yet."""

    device = DEVICE_NAME

    def __init__(self, *, width: int, height: int, fps: float, check_install: bool = True):
        if sys.platform != "win32":
            raise RuntimeError("虚拟摄像头输出目前仅支持 Windows；其他系统可以体验界面。")
        if check_install:
            import winreg

            try:
                with winreg.OpenKey(
                    winreg.HKEY_CLASSES_ROOT,
                    rf"CLSID\{SERVICE_CLSID}\InprocServer32",
                    access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ):
                    pass
            except OSError as exc:
                raise RuntimeError(
                    "尚未安装虚拟摄像头组件。请打开开始菜单中的「安装虚拟摄像头组件」，"
                    "完成后重新打开通话或直播软件。"
                ) from exc
        self.width, self.height, self.fps = width, height, fps
        self._handles: dict[str, int] = {}
        self._view = None
        self._receiver_seen_at: float | None = None
        self._api = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_api()
        # Only one app instance may publish to this named camera.
        owner = self._api.CreateMutexW(None, False, "FSSCapture_Publisher")
        existed = ctypes.get_last_error() == 183
        if not owner:
            raise ctypes.WinError(ctypes.get_last_error())
        if existed:
            self._api.CloseHandle(owner)
            raise RuntimeError("虚拟摄像头正在被另一个 FaceSwap Studio 窗口使用，请先停止其输出。")
        self._handles["owner"] = owner

    def _configure_api(self):
        from ctypes import wintypes as w

        signatures = {
            "OpenMutexW": ([w.DWORD, w.BOOL, w.LPCWSTR], w.HANDLE),
            "CreateMutexW": ([ctypes.c_void_p, w.BOOL, w.LPCWSTR], w.HANDLE),
            "CreateEventW": ([ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR], w.HANDLE),
            "OpenEventW": ([w.DWORD, w.BOOL, w.LPCWSTR], w.HANDLE),
            "OpenFileMappingW": ([w.DWORD, w.BOOL, w.LPCWSTR], w.HANDLE),
            "MapViewOfFile": ([w.HANDLE, w.DWORD, w.DWORD, w.DWORD, ctypes.c_size_t], ctypes.c_void_p),
            "UnmapViewOfFile": ([ctypes.c_void_p], w.BOOL),
            "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
            "ReleaseMutex": ([w.HANDLE], w.BOOL),
            "SetEvent": ([w.HANDLE], w.BOOL),
            "CloseHandle": ([w.HANDLE], w.BOOL),
        }
        for name, (args, ret) in signatures.items():
            func = getattr(self._api, name)
            func.argtypes, func.restype = args, ret

    def _connect(self) -> bool:
        if self._view:
            return True
        api, handles = self._api, self._handles
        if "mutex" not in handles:
            # SYNCHRONIZE | MUTEX_MODIFY_STATE, with a finite wait in send().
            handle = api.OpenMutexW(0x00100001, False, "FSSCapture_Mutx")
            if not handle:
                return False
            handles["mutex"] = handle
        if "want" not in handles:
            handle = api.CreateEventW(None, False, False, "FSSCapture_Want")
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            handles["want"] = handle
        if "sent" not in handles:
            handle = api.OpenEventW(0x0002, False, "FSSCapture_Sent")
            if not handle:
                return False
            handles["sent"] = handle
        if "mapping" not in handles:
            handle = api.OpenFileMappingW(0x0002, False, "FSSCapture_Data")
            if not handle:
                return False
            handles["mapping"] = handle
        self._view = api.MapViewOfFile(handles["mapping"], 0x0002, 0, 0, 0)
        if not self._view:
            raise ctypes.WinError(ctypes.get_last_error())
        return True

    def send(self, image: np.ndarray) -> bool:
        if not self._connect():
            return False
        pixels = encode_rgba(image)
        result = self._api.WaitForSingleObject(self._handles["mutex"], 40)
        if result == 258:  # WAIT_TIMEOUT: skip, never block the capture pipeline.
            return False
        if result not in (0, 128):  # WAIT_OBJECT_0 / WAIT_ABANDONED
            raise RuntimeError("虚拟摄像头共享内存连接异常，请停止输出后重试。")
        try:
            capacity = ctypes.c_uint32.from_address(self._view).value
            if capacity > MAX_IMAGE_BYTES or pixels.nbytes > capacity:
                raise RuntimeError("虚拟摄像头图像大小不匹配，请重启接收软件。")
            # DWORD capacity is owned by the receiver. Seven 32-bit fields follow.
            header = struct.pack("<7i", self.width, self.height, self.width, 0, 1, 0, 1000)
            ctypes.memmove(self._view + 4, header, len(header))
            ctypes.memmove(self._view + HEADER_SIZE, pixels.ctypes.data, pixels.nbytes)
        finally:
            self._api.ReleaseMutex(self._handles["mutex"])
        self._api.SetEvent(self._handles["sent"])
        if self._api.WaitForSingleObject(self._handles["want"], 0) == 0:
            self._receiver_seen_at = time.monotonic()
        return (
            self._receiver_seen_at is not None
            and time.monotonic() - self._receiver_seen_at < 0.75
        )

    def close(self):
        if self._view:
            self._api.UnmapViewOfFile(self._view)
            self._view = None
        for handle in self._handles.values():
            self._api.CloseHandle(handle)
        self._handles.clear()
        self._receiver_seen_at = None
