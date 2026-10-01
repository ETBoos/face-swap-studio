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
        progress("正在预热模型并检查输出…")
        validate_prediction(self.model.convert(np.zeros((width, width, 3), np.float32)), width, np)
        self.detector.extract(np.zeros((480, 640, 3), np.uint8), fixed_window=640)
        self.marker.extract(np.zeros((192, 192, 3), np.uint8))

    def placeholder(self, frame, reason):
        return self.np.full_like(frame, 24), False, reason

    def process(self, frame):
        np, cv2 = self.np, self.cv2
        height, width = frame.shape[:2]
        faces = self.detector.extract(frame, threshold=0.5, fixed_window=640, min_face_size=40)[0]
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
        # Whole-face alignment matches upstream's default coverage and vertical offset.
        aligned, matrix = landmarks.cut(frame, 2.2, self.resolution,
                                        exclude_moving_parts=True, y_offset=-0.08)
        swapped, celeb_mask, source_mask = validate_prediction(
            self.model.convert(aligned.astype(np.float32) / 255.0), self.resolution, np,
        )
        # Both masks must agree. The model can emit a rectangular background
        # around the aligned face; keep that area outside the face landmarks.
        mask = (celeb_mask * source_mask)[:, :, 0]
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

        # Match DeepFaceLive's default 5-pixel erosion, 25-pixel blur and
        # fade-to-border behavior. Without the border fade, OpenCV's black
        # padding is blended into the camera as a dark square.
        side = self.resolution
        mask = np.pad(mask, ((side, side), (side, side)))
        mask = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
                         iterations=2)
        fade = 25 // 2
        mask[:side + fade, :] = mask[-side - fade:, :] = 0
        mask[:, :side + fade] = mask[:, -side - fade:] = 0
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=25 * 0.25)
        mask = mask[side:-side, side:-side]
        affine = matrix.invert().to_exact_mat(self.resolution, self.resolution, width, height)
        if not np.isfinite(affine).all():
            return self.placeholder(frame, "人脸角度暂时无法对齐")
        full_mask = cv2.warpAffine(mask, affine, (width, height))[:, :, None]
        if np.count_nonzero(full_mask > 0.1) < 64:
            return self.placeholder(frame, "模型没有生成有效面部蒙版")
        full_face = cv2.warpAffine(swapped, affine, (width, height))
        l, t, r, b = rectangle
        margin = max(r - l, b - t) * 0.35
        x0, y0 = max(0, int(l - margin)), max(0, int(t - margin))
        x1, y1 = min(width, int(r + margin)), min(height, int(b + margin))
        visible_mask = full_mask[:, :, 0] > 0.1
        near_face = np.zeros((height, width), dtype=bool)
        near_face[y0:y1, x0:x1] = True
        if np.count_nonzero(visible_mask & near_face) < 0.65 * np.count_nonzero(visible_mask):
            return self.placeholder(frame, "换脸区域偏离人脸，输出已暂停")
        face_core = full_mask[:, :, 0] > 0.3
        if not np.count_nonzero(face_core):
            return self.placeholder(frame, "面部蒙版太弱，输出已暂停")
        black_pixels = (full_face.max(axis=2) < 0.03) & (frame.mean(axis=2) > 25)
        if np.count_nonzero(black_pixels & face_core) > 0.25 * np.count_nonzero(face_core):
            return self.placeholder(frame, "模型输出大面积黑色，输出已暂停")
        face_area = face_core & near_face
        change = np.abs(full_face * 255 - frame.astype(np.float32)).mean(axis=2)
        if np.count_nonzero(face_area) < 64 or change[face_area].mean() < 3:
            return self.placeholder(frame, "模型没有明显改变脸部，输出已暂停")
        result = np.clip(frame.astype(np.float32) * (1 - full_mask) + full_face * 255 * full_mask,
                         0, 255).astype(np.uint8)
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
            }
            write_message(output, {"type": "frame", "width": result.shape[1],
                                   "height": result.shape[0], "format": "bgr24",
                                   "fps": 0 if previous_ns is None else 1e9 / max(1, now - previous_ns),
                                   "meta": meta}, result.tobytes())
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
