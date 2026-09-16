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

from face_swap_studio.core.cameras import directshow_camera_names
from face_swap_studio.outputs.unity_camera import DEVICE_NAME, UnityCamera


def main():
    if sys.platform != "win32":
        raise RuntimeError("This smoke check requires Windows.")
    names = directshow_camera_names()
    print("Video inputs:", names, flush=True)
    if names != [DEVICE_NAME]:
        raise RuntimeError("Pixel smoke expects only our generated virtual camera; refusing physical devices.")
    from probe_directshow import main as probe_graph
    probe_graph()
    sender = UnityCamera(width=640, height=480, fps=30)
    stop = threading.Event()
    errors = []
    pixels = np.empty((480, 640, 3), np.uint8)
    colours = [(17, 80, 210), (140, 40, 30), (30, 180, 60), (210, 160, 40)]
    pixels[:240, :320] = colours[0]
    pixels[:240, 320:] = colours[1]
    pixels[240:, :320] = colours[2]
    pixels[240:, 320:] = colours[3]

    def publish():
        try:
            index = 0
            while not stop.is_set():
                stamp = (32, 96, 160, 224)[(index // 3) % 4]
                pixels[160:320, 240:400] = stamp
                sender.send(pixels)
                index += 1
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
        seen_stamps = set()
        while time.monotonic() < end:
            if errors:
                raise errors[0]
            ok, frame = capture.read()
            if ok and frame is not None:
                if frame.shape != (480, 640, 3):
                    raise RuntimeError(f"Unexpected capture dimensions: {frame.shape}; expected 480x640x3")
                height, width = frame.shape[:2]
                corners = [frame[height // 6, width // 6], frame[height // 6, 5 * width // 6],
                           frame[5 * height // 6, width // 6], frame[5 * height // 6, 5 * width // 6]]
                if np.allclose(corners, colours, atol=4):
                    centre = frame[height // 2, width // 2]
                    for stamp in (32, 96, 160, 224):
                        if np.allclose(centre, stamp, atol=4):
                            seen_stamps.add(stamp)
                    count += 1
                    if count >= 5 and len(seen_stamps) >= 3:
                        print("PASS: BGR colours, orientation and changing frames traversed IPC -> DirectShow -> OpenCV", flush=True)
                        break
        else:
            raise RuntimeError("Correct orientation, colours or changing pixels were not received.")
        stop.set()
        worker.join(timeout=2)
        sender.close()
        deadline = time.monotonic() + 2.5
        while time.monotonic() < deadline:
            ok, frame = capture.read()
            if ok and frame is not None and np.max(frame) <= 3:
                print("PASS: stopping publisher produced a black frame within 2.5 seconds", flush=True)
                return
        raise RuntimeError("Camera kept an old frame after the publisher stopped.")
    finally:
        stop.set()
        worker.join(timeout=2)
        capture.release()
        sender.close()


if __name__ == "__main__":
    main()
