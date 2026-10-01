# SPDX-License-Identifier: GPL-3.0-only
"""Headless integration with iperov/DeepFaceLive's DFM and geometry APIs.

Upstream API reference: fc7b787bda2b8c186e142c52857458eea3a935ed.
Runs in the installed NVIDIA runtime; never imports Qt or launches main.py.
This integration file is distributed as source with GPL-3.0 (see notices).
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

if __package__:
    from .facefusion_protocol import MAX_CONFIG_BYTES, write_message
    from .facefusion_worker import LatestCapture, fit_frame
else:
    from facefusion_protocol import MAX_CONFIG_BYTES, write_message
    from facefusion_worker import LatestCapture, fit_frame

ENGINE_VERSION = "dfl-headless-1"


class AdaptiveLandmarks:
    """Filter small landmark jitter, without averaging rendered frames or expressions."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.previous = None
        self.updated = None

    def update(self, points, face_size, now, np):
        previous = self.previous
        if previous is not None and self.updated is not None:
            dt = now - self.updated
            if 0 < dt < 0.3 and previous.shape == points.shape:
                # Normalized displacement relative to face size, independent of preview size.
                movement = float(np.linalg.norm(points - previous, axis=1).mean())
                speed = movement / max(face_size, 1e-6)
                alpha = float(np.clip(0.4 + speed * 20, 0.4, 1.0))
                # A low frame rate must not add a multi-frame tracking delay.
                alpha = 1 - (1 - alpha) ** max(1.0, dt * 30)
                points = previous + alpha * (points - previous)
        self.previous, self.updated = points.copy(), now
        return points


def match_face_color(face, original, mask, cv2, np):
    """Bounded Lab correction in the face core; preserve texture and exclude highlights."""
    source = cv2.cvtColor(np.ascontiguousarray(face), cv2.COLOR_BGR2LAB)
    target = cv2.cvtColor(original.astype(np.float32) / 255, cv2.COLOR_BGR2LAB)
    selected = (mask > 0.6) & (source[:, :, 0] > 10) & (source[:, :, 0] < 95)
    selected &= (target[:, :, 0] > 10) & (target[:, :, 0] < 95)
    if np.count_nonzero(selected) < 64:
        return face
    delta = target[selected].mean(axis=0) - source[selected].mean(axis=0)
    delta = np.clip(delta, (-10, -6, -6), (10, 6, 6)).astype(np.float32) * 0.65
    source += delta
    source[:, :, 0] = np.clip(source[:, :, 0], 0, 100)
    return np.clip(cv2.cvtColor(source, cv2.COLOR_LAB2BGR), 0, 1)


def warp_face_region(face, mask, affine, frame_shape, cv2, np):
    """Warp only the aligned face's visible bounding box, not an entire HD frame."""
    height, width = frame_shape[:2]
    side = mask.shape[0]
    corners = np.float32([[[0, 0], [side, 0], [side, side], [0, side]]])
    corners = cv2.transform(corners, affine)[0]
    x0, y0 = np.maximum(np.floor(corners.min(axis=0) - 2), (0, 0)).astype(int)
    x1, y1 = np.minimum(np.ceil(corners.max(axis=0) + 2), (width, height)).astype(int)
    if x1 <= x0 or y1 <= y0:
        return None
    local = affine.astype(np.float64)
    local[:, 2] -= (x0, y0)
    size = (int(x1 - x0), int(y1 - y0))
    return (int(x0), int(y0), int(x1), int(y1),
            cv2.warpAffine(face, local, size), cv2.warpAffine(mask, local, size))


def require_cuda(model, name):
    session = getattr(model, "_sess", None)
    if session is None or "CUDAExecutionProvider" not in session.get_providers():
        raise RuntimeError(f"{name} 未启用 NVIDIA CUDA；请检查引擎自带 CUDA/cuDNN 与显卡驱动，未回退 CPU")
    # Prevent ONNX Runtime retrying a failed run on CPU.
    disable = getattr(session, "disable_fallback", None)
    if callable(disable):
        disable()


def validate_prediction(prediction, resolution, np):
    if not isinstance(prediction, (tuple, list)) or len(prediction) != 3:
        raise RuntimeError("DFM 输出结构不兼容，需要人脸、目标蒙版、原脸蒙版")
    result = []
    for value, channels in zip(prediction, (3, 1, 1)):
        if value.shape != (1, resolution, resolution, channels) or not np.isfinite(value).all():
            raise RuntimeError("DFM 输出尺寸或数值无效；请重新导出兼容 DeepFaceLive 的模型")
        result.append(np.clip(value[0].astype(np.float32), 0, 1))
    return result


class DeepFaceLivePipeline:
    def __init__(self, config, progress):
        import cv2
        import numpy as np
        from modelhub.DFLive.DFMModel import DFMModel
        from modelhub.onnx import InsightFace2D106, YoloV5Face
        from xlib.face import ELandmarks2D, FLandmarks2D, FRect
        from xlib.onnxruntime import get_available_devices_info

        self.cv2, self.np, self.config = cv2, np, config
        self.FRect, self.FLandmarks2D, self.ELandmarks2D = FRect, FLandmarks2D, ELandmarks2D
        devices = [d for d in get_available_devices_info(include_cpu=False)
                   if d.get_execution_provider() == "CUDAExecutionProvider"
                   and d.get_index() == config["device_id"]]
        if not devices:
            raise RuntimeError("未找到所选 NVIDIA GPU；请检查 cuda:0 编号、驱动和 NVIDIA 引擎安装包")
        device = devices[0]
        progress("正在加载人脸检测器…")
        self.detector = YoloV5Face(device)
        require_cuda(self.detector, "人脸检测器")
        progress("正在加载面部定位器…")
        self.marker = InsightFace2D106(device)
        require_cuda(self.marker, "面部定位器")
        progress("正在加载专用人物模型，首次启动可能较慢…")
        self.model = DFMModel(Path(config["dfm_path"]), device)
        require_cuda(self.model, "DFM 模型")
        width, height = self.model.get_input_res()
        if type(width) is not int or type(height) is not int or width != height or not 64 <= width <= 640:
            raise RuntimeError("此版本支持 64–640 分辨率的正方形 DFM 模型；当前模型输入不兼容")
        self.resolution = width
        self.tracker = AdaptiveLandmarks()
        self.frame_shape = None
        self.timings = {}
        progress("正在预热模型并检查输出…")
        validate_prediction(self.model.convert(np.zeros((width, width, 3), np.float32)), width, np)
        self.detector.extract(np.zeros((480, 640, 3), np.uint8), fixed_window=640)
        self.marker.extract(np.zeros((192, 192, 3), np.uint8))

    def placeholder(self, frame, reason):
        self.tracker.reset()
        return self.np.full_like(frame, 24), False, reason

    def process(self, frame):
        np, cv2 = self.np, self.cv2
        started = time.perf_counter()
        self.timings = {}
        height, width = frame.shape[:2]
        if self.frame_shape != frame.shape:
            self.tracker.reset()
            self.frame_shape = frame.shape
        faces = self.detector.extract(frame, threshold=0.5, fixed_window=640, min_face_size=40)[0]
        self.timings["detect_ms"] = (time.perf_counter() - started) * 1000
        if len(faces) != 1:
            return self.placeholder(frame, "未检测到清晰人脸" if not faces else "检测到多张人脸，输出已暂停")
        rectangle = np.asarray(faces[0], dtype=np.float32)
        if rectangle.shape != (4,) or not np.isfinite(rectangle).all():
            return self.placeholder(frame, "人脸定位不稳定，请正对摄像头")
        rect = self.FRect.from_ltrb(rectangle / (width, height, width, height))
        marker_image, marker_matrix = rect.cut(frame, 1.6, 192)
        points = self.marker.extract(marker_image)[0]
        if points.shape != (106, 2) or not np.isfinite(points).all():
            return self.placeholder(frame, "面部关键点不稳定，请调整光线")
        landmarks = self.FLandmarks2D.create(self.ELandmarks2D.L106, points / (192, 192))
        landmarks = landmarks.transform(marker_matrix, invert=True)
        tracked = self.tracker.update(
            landmarks.as_numpy(w_h=(width, height)),
            max(rectangle[2] - rectangle[0], rectangle[3] - rectangle[1]),
            time.monotonic(), np,
        )
        landmarks = self.FLandmarks2D.create(self.ELandmarks2D.L106, tracked / (width, height))
        # Whole-face alignment matches upstream's default coverage and vertical offset.
        aligned, matrix = landmarks.cut(frame, 2.2, self.resolution,
                                        exclude_moving_parts=True, y_offset=-0.08)
        before_model = time.perf_counter()
        self.timings["align_ms"] = (before_model - started) * 1000 - self.timings["detect_ms"]
        swapped, celeb_mask, source_mask = validate_prediction(
            self.model.convert(aligned.astype(np.float32) / 255.0), self.resolution, np,
        )
        self.timings["model_ms"] = (time.perf_counter() - before_model) * 1000
        before_merge = time.perf_counter()
        # Both masks must agree. The model can emit a rectangular background
        # around the aligned face; keep that area outside the face landmarks.
        if float((celeb_mask * source_mask).max()) <= 0.3:
            return self.placeholder(frame, "面部蒙版太弱，输出已暂停")
        # Intersection without squaring soft alpha: multiplication let the original
        # features show through otherwise healthy semi-transparent model masks.
        mask = np.minimum(celeb_mask, source_mask)[:, :, 0]
        aligned_landmarks = landmarks.transform(matrix)
        hull = aligned_landmarks.get_convexhull_mask(
            (self.resolution, self.resolution), dtype=np.float32,
        )[:, :, 0]
        hull_size = max(3, (self.resolution // 16) | 1)
        hull = cv2.dilate(hull, cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (hull_size, hull_size),
        ))
        mask *= hull
        if np.count_nonzero(mask > 0.25) < max(32, self.resolution**2 // 100):
            return self.placeholder(frame, "模型没有生成足够的面部蒙版")

        # Feather at model scale, with zero padding and a fade at the crop border.
        # Do not blur the generated face itself.
        side = self.resolution
        padding = max(4, round(side * 0.05))
        mask = np.pad(mask, ((padding, padding), (padding, padding)))
        mask = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
                         iterations=max(1, round(side / 224)))
        fade = max(1, round(side * 0.025))
        mask[:padding + fade, :] = mask[-padding - fade:, :] = 0
        mask[:, :padding + fade] = mask[:, -padding - fade:] = 0
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=max(1.0, side * 0.015))
        mask = mask[padding:-padding, padding:-padding]
        affine = matrix.invert().to_exact_mat(self.resolution, self.resolution, width, height)
        if not np.isfinite(affine).all():
            return self.placeholder(frame, "人脸角度暂时无法对齐")
        region = warp_face_region(swapped, mask, affine, frame.shape, cv2, np)
        if region is None:
            return self.placeholder(frame, "换脸区域超出画面")
        rx0, ry0, rx1, ry1, full_face, roi_mask = region
        original = frame[ry0:ry1, rx0:rx1]
        full_mask = roi_mask[:, :, None]
        if np.count_nonzero(full_mask > 0.1) < 64:
            return self.placeholder(frame, "模型没有生成有效面部蒙版")
        l, t, r, b = rectangle
        margin = max(r - l, b - t) * 0.35
        x0, y0 = max(0, int(l - margin)), max(0, int(t - margin))
        x1, y1 = min(width, int(r + margin)), min(height, int(b + margin))
        visible_mask = full_mask[:, :, 0] > 0.1
        near_face = np.zeros(original.shape[:2], dtype=bool)
        nx0, ny0 = max(x0, rx0) - rx0, max(y0, ry0) - ry0
        nx1, ny1 = min(x1, rx1) - rx0, min(y1, ry1) - ry0
        if nx1 > nx0 and ny1 > ny0:
            near_face[ny0:ny1, nx0:nx1] = True
        if np.count_nonzero(visible_mask & near_face) < 0.65 * np.count_nonzero(visible_mask):
            return self.placeholder(frame, "换脸区域偏离人脸，输出已暂停")
        face_core = full_mask[:, :, 0] > 0.3
        if not np.count_nonzero(face_core):
            return self.placeholder(frame, "面部蒙版太弱，输出已暂停")
        black_pixels = (full_face.max(axis=2) < 0.03) & (original.mean(axis=2) > 25)
        if np.count_nonzero(black_pixels & face_core) > 0.25 * np.count_nonzero(face_core):
            return self.placeholder(frame, "模型输出大面积黑色，输出已暂停")
        face_area = face_core & near_face
        change = np.abs(full_face * 255 - original.astype(np.float32)).mean(axis=2)
        if np.count_nonzero(face_area) < 64 or change[face_area].mean() < 3:
            return self.placeholder(frame, "模型没有明显改变脸部，输出已暂停")
        # Validate the raw prediction before color correction can conceal a broken model.
        corrected = match_face_color(swapped, aligned, mask, cv2, np)
        local_affine = affine.astype(np.float64)
        local_affine[:, 2] -= (rx0, ry0)
        full_face = cv2.warpAffine(corrected, local_affine, (rx1 - rx0, ry1 - ry0))
        result = frame.copy()
        result[ry0:ry1, rx0:rx1] = np.clip(
            original.astype(np.float32) * (1 - full_mask) + full_face * 255 * full_mask,
            0, 255).astype(np.uint8)
        self.timings["merge_ms"] = (time.perf_counter() - before_merge) * 1000
        if self.config.get("watermark"):
            text = str(self.config["watermark"])
            if not text.isascii():
                text = "FaceSwap Studio Preview"
            cv2.putText(result, text[:120], (12, height - 16), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (245, 245, 245), 1, cv2.LINE_AA)
        return np.ascontiguousarray(result), True, "swapped"


def run(config, output):
    if config.get("version") != ENGINE_VERSION:
        raise RuntimeError("专用模型引擎版本不匹配，请重新安装当前软件")
    source = Path(config["source_root"]).resolve()
    os.chdir(source)
    sys.path.insert(0, str(source))

    def progress(message):
        write_message(output, {"type": "status", "message": message})

    progress("正在检查显卡与引擎环境…")
    pipeline = DeepFaceLivePipeline(config, progress)
    capture = LatestCapture(config, pipeline.cv2)
    try:
        progress("正在打开摄像头…")
        capture.start()
        item = capture.take()
        write_message(output, {"type": "ready", "engine_version": ENGINE_VERSION})
        progress("模型已加载，请正对摄像头，等待换脸首帧…")
        previous_ns = None
        last_report = time.monotonic()
        while True:
            frame_id, captured_at, captured_ns, frame = item
            start = time.monotonic_ns()
            frame = fit_frame(frame, config["width"], config["height"], pipeline.cv2)
            result, swapped, reason = pipeline.process(frame)
            now = time.monotonic_ns()
            meta = {
                "frame_id": frame_id, "captured_at_ns": captured_at,
                "captured_monotonic_ns": captured_ns, "processed_at_ns": time.time_ns(),
                "processed_monotonic_ns": now, "processing_ms": (now - start) / 1e6,
                "capture_to_processed_ms": (now - captured_ns) / 1e6,
                "stub": False, "face_swapped": swapped, "safe_to_output": swapped,
                "placeholder": not swapped, "reason": reason, "engine_version": ENGINE_VERSION,
                "execution_provider": "cuda",
                "stage_ms": pipeline.timings,
            }
            write_message(output, {"type": "frame", "width": result.shape[1],
                                   "height": result.shape[0], "format": "bgr24",
                                   "fps": 0 if previous_ns is None else 1e9 / max(1, now - previous_ns),
                                   "meta": meta}, result.tobytes())
            if time.monotonic() - last_report >= 10:
                print("DFM performance " + json.dumps({
                    "stage_ms": pipeline.timings,
                    "processing_ms": meta["processing_ms"],
                    "capture_to_processed_ms": meta["capture_to_processed_ms"],
                    "send_ms": (time.monotonic_ns() - now) / 1e6,
                }), file=sys.stderr, flush=True)
                last_report = time.monotonic()
            previous_ns = now
            item = capture.take()
    finally:
        capture.stop()


def main():
    output = os.fdopen(os.dup(sys.stdout.fileno()), "wb")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    handles = []
    try:
        raw = sys.stdin.buffer.readline(MAX_CONFIG_BYTES + 1)
        if not raw or len(raw) > MAX_CONFIG_BYTES:
            raise RuntimeError("专用模型配置缺失或过大")
        config = json.loads(raw)
        if not isinstance(config, dict):
            raise TypeError("专用模型配置格式无效")
        if sys.platform == "win32":
            root = Path(config["root"])
            for path in (root / "_internal/CUDA/bin", root / "_internal/CUDA",
                         Path(sys.prefix), Path(sys.prefix) / "DLLs"):
                if path.is_dir():
                    handles.append(os.add_dll_directory(str(path)))
        run(config, output)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - report native/upstream failures to UI
        traceback.print_exc(file=sys.stderr)
        try:
            write_message(output, {"type": "error", "message": f"{type(exc).__name__}: {exc}"[:4000]})
        except (OSError, ValueError):
            pass
        return 1
    finally:
        output.close()
        for handle in handles:
            handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
