"""Windows CI pixel test using a generated colour field, never a physical camera.

Run after installing the camera component, with no physical cameras attached.
The parent must impose a process timeout in case a platform capture call hangs.
"""
from __future__ import annotations

import sys
import threading
import time

import cv2
import numpy as np
from PySide6.QtCore import QCoreApplication
from PySide6.QtMultimedia import QMediaDevices

from face_swap_studio.outputs.unity_camera import DEVICE_NAME, UnityCamera


def main():
    if sys.platform != "win32":
        raise RuntimeError("This smoke check requires Windows.")
    app = QCoreApplication.instance() or QCoreApplication([])
    names = [device.description() for device in QMediaDevices.videoInputs()]
    print("Video inputs:", names, flush=True)
    if names != [DEVICE_NAME]:
        raise RuntimeError("Pixel smoke expects only our generated virtual camera; refusing physical devices.")
    sender = UnityCamera(width=640, height=480, fps=30)
    stop = threading.Event()
    errors = []
    pixels = np.full((480, 640, 3), (17, 80, 210), np.uint8)

    def publish():
        try:
            while not stop.is_set():
                sender.send(pixels)
                stop.wait(1 / 30)
        except Exception as exc:  # noqa: BLE001 — propagate worker errors to main
            errors.append(exc)

    worker = threading.Thread(target=publish, daemon=True)
    worker.start()
    capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    try:
        if not capture.isOpened():
            raise RuntimeError("DirectShow failed to open the installed camera.")
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        end = time.monotonic() + 15
        count = 0
        while time.monotonic() < end:
            if errors:
                raise errors[0]
            ok, frame = capture.read()
            if ok and frame is not None:
                centre = frame[frame.shape[0] // 2, frame.shape[1] // 2]
                if np.allclose(centre, (17, 80, 210), atol=4):
                    count += 1
                    if count >= 5:
                        print("PASS: five generated BGR frames traversed IPC -> DirectShow -> OpenCV", flush=True)
                        return
        raise RuntimeError("No correct synthetic pixels received through the virtual camera.")
    finally:
        stop.set()
        worker.join(timeout=2)
        capture.release()
        sender.close()
        del app


if __name__ == "__main__":
    main()
