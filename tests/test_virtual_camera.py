from __future__ import annotations

import ctypes
import time

import numpy as np
import pytest

from face_swap_studio.engines.base import EngineFrame
from face_swap_studio.outputs.unity_camera import UnityCamera, encode_rgba
from face_swap_studio.outputs.virtual_camera import OutputStatus, VirtualCameraOutput


def wait_for(predicate, timeout=2):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.005)
    assert predicate()


class Receiver:
    device = "test camera"

    def __init__(self, **kwargs):
        self.frames = []
        self.closed = False

    def send(self, frame):
        self.frames.append(frame.copy())
        return True

    def close(self):
        self.closed = True


def safe_frame(value=180):
    return EngineFrame(
        np.full((24, 32, 3), value, np.uint8),
        meta={"stub": False, "face_swapped": True, "safe_to_output": True},
    )


def test_output_copies_frames_and_blanks_on_stale_or_pause():
    receiver = Receiver()
    output = VirtualCameraOutput(camera_factory=lambda **kw: receiver, stale_timeout=0.08)
    output.start(32, 24, 120)
    try:
        wait_for(lambda: output.status() == OutputStatus.RUNNING)
        frame = safe_frame()
        assert output.send(frame)
        frame.image[:] = 0  # producer reuse must not modify queued frame
        wait_for(lambda: any(np.all(f == 180) for f in receiver.frames))
        wait_for(lambda: output.status() == OutputStatus.PAUSED)
        wait_for(lambda: np.all(receiver.frames[-1] == (32, 28, 24)))
        assert "中断" in output.last_error()
        assert output.send(safe_frame(90))
        wait_for(lambda: np.all(receiver.frames[-1] == 90))
        output.pause("用户暂停")
        wait_for(lambda: np.all(receiver.frames[-1] == (32, 28, 24)))
        output.start(32, 24, 120)
        assert output.status() == OutputStatus.RUNNING
        assert output.send(safe_frame(70))
        wait_for(lambda: np.all(receiver.frames[-1] == 70))
    finally:
        output.stop()
        wait_for(lambda: receiver.closed)


@pytest.mark.parametrize("meta", [{}, {"stub": True}, {"stub": False},
    {"stub": False, "face_swapped": True},
    {"stub": False, "face_swapped": True, "safe_to_output": False}])
def test_unsafe_and_placeholder_frames_never_reach_device(meta):
    receiver = Receiver()
    output = VirtualCameraOutput(camera_factory=lambda **kw: receiver)
    output.start(32, 24, 120)
    try:
        wait_for(lambda: output.status() == OutputStatus.RUNNING)
        assert not output.send(EngineFrame(np.full((24, 32, 3), 255, np.uint8), meta=meta))
        wait_for(lambda: len(receiver.frames) >= 2)
        assert all(not np.all(frame == 255) for frame in receiver.frames)
        assert output.status() == OutputStatus.PAUSED
    finally:
        output.stop()
        wait_for(lambda: receiver.closed)


def test_driver_error_is_visible_and_can_retry():
    def unavailable(**kw):
        raise RuntimeError("需要安装组件")
    output = VirtualCameraOutput(camera_factory=unavailable)
    output.start(32, 24, 30)
    wait_for(lambda: output.status() == OutputStatus.ERROR)
    assert "需要安装组件" in output.last_error()
    wait_for(lambda: not output._thread.is_alive())
    receiver = Receiver()
    output._factory = lambda **kw: receiver
    output.start(32, 24, 30)
    wait_for(lambda: output.status() == OutputStatus.RUNNING)
    output.stop()
    wait_for(lambda: receiver.closed)


def test_invalid_frame_dimensions_pause_and_bgr_channels_are_preserved():
    receiver = Receiver()
    output = VirtualCameraOutput(camera_factory=lambda **kw: receiver)
    output.start(32, 24, 30)
    try:
        frame = safe_frame()
        frame.image = frame.image[:12]
        assert not output.send(frame)
        assert "尺寸" in output.last_error()
    finally:
        output.stop()
        wait_for(lambda: receiver.closed)
    np.testing.assert_array_equal(
        encode_rgba(np.array([[[3, 2, 1]], [[6, 5, 4]]], dtype=np.uint8)),
        np.array([[[4, 5, 6, 255]], [[1, 2, 3, 255]]], dtype=np.uint8),
    )


@pytest.mark.parametrize("fps", [float("nan"), float("inf"), 0, 121])
def test_invalid_fps_does_not_launch_a_worker(fps):
    output = VirtualCameraOutput()
    with pytest.raises(ValueError):
        output.start(32, 24, fps)
    assert output.status() == OutputStatus.STOPPED


def test_receiver_connected_requires_live_request_events(monkeypatch):
    """A mapped buffer alone must not look like an active receiving call."""
    from face_swap_studio.outputs import unity_camera

    now = [5.0]
    monkeypatch.setattr(unity_camera.time, "monotonic", lambda: now[0])
    buffer = ctypes.create_string_buffer(32 + 2 * 4)
    ctypes.c_uint32.from_buffer(buffer).value = 8

    class API:
        requesting = True

        def WaitForSingleObject(self, handle, timeout):
            return 0 if handle == "mutex" or self.requesting else 258

        def ReleaseMutex(self, handle):
            return True

        def SetEvent(self, handle):
            return True

    camera = UnityCamera.__new__(UnityCamera)
    camera.width, camera.height = 1, 2
    camera._handles = {name: name for name in ("mutex", "want", "sent")}
    camera._view = ctypes.addressof(buffer)
    camera._receiver_seen_at = None
    camera._api = API()
    pixels = np.array([[[3, 2, 1]], [[6, 5, 4]]], np.uint8)
    assert camera.send(pixels)
    assert bytes(buffer)[32:40] == bytes([4, 5, 6, 255, 1, 2, 3, 255])
    camera._api.requesting = False
    now[0] += 0.8
    assert not camera.send(pixels)
    camera._api.requesting = True
    assert camera.send(pixels)
