"""External-Python worker for the audited official FaceFusion 3.9.0 API.

Executed by path, not ``-m``: this file never imports the desktop application or
Qt. It imports the user's FaceFusion install, validates existing model hashes,
and invokes its detection/embedding/swap/mask functions. No models are bundled
or downloaded. Single-person output only; uncertain frames become placeholders.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
import zlib
from pathlib import Path
from typing import Any

if __package__:
    from .facefusion_protocol import MAX_CONFIG_BYTES, write_message
else:
    from facefusion_protocol import MAX_CONFIG_BYTES, write_message

SUPPORTED_VERSION = "3.9.0"
SUPPORTED_MODELS = {"inswapper_128", "inswapper_128_fp16"}
PROVIDER_NAMES = {
    "cuda": "CUDAExecutionProvider", "cpu": "CPUExecutionProvider",
    "directml": "DmlExecutionProvider", "coreml": "CoreMLExecutionProvider",
}


def validate_local_hashes(hash_set: dict[str, Any]) -> bool:
    for entry in hash_set.values():
        path = Path(entry["path"])
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            raise RuntimeError(f"缺少模型校验文件：{path}；请在 FaceFusion 中准备模型后重试（此程序不会下载）")
    return True


def validate_local_sources(source_set: dict[str, Any]) -> bool:
    """Match FaceFusion 3.9.0's CRC32 sidecars, without loading GBs into RAM."""
    for entry in source_set.values():
        path = Path(entry["path"])
        sidecar = path.with_suffix(".hash")
        if not path.is_file() or not sidecar.is_file():
            raise RuntimeError(f"缺少模型或 .hash 文件：{path}；请在 FaceFusion 中准备模型后重试（此程序不会下载）")
        checksum = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                checksum = zlib.crc32(chunk, checksum)
        expected = sidecar.read_text(encoding="utf-8").strip()
        if f"{checksum:08x}" != expected:
            raise RuntimeError(f"模型校验不通过：{path.name}；请修复该模型，原文件未被修改")
    return True


def install_offline_download_guard(download_module: Any) -> None:
    """Applied before importing model modules that bind download functions."""
    def deny_download(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("适配器禁止自动下载；请在已安装的 FaceFusion 中准备完整模型")

    download_module.conditional_download_hashes = validate_local_hashes
    download_module.conditional_download_sources = validate_local_sources
    download_module.conditional_download = deny_download
    download_module.open_curl = deny_download
    # Model catalog construction otherwise probes remote provider URLs.
    download_module.resolve_download_url = lambda *_args, **_kwargs: None


def state_defaults(config: dict[str, Any]) -> dict[str, Any]:
    """Explicit audited configuration; no user facefusion.ini or CLI side effects."""
    return {
        "command": "run", "source_paths": config["source_paths"],
        "processors": ["face_swapper"], "execution_device_ids": [config["device_id"]],
        "execution_providers": [config["provider"]], "execution_thread_count": 1,
        "download_providers": [], "download_scope": "full", "log_level": "error",
        "video_memory_strategy": "tolerant", "workflow_mode": "image-to-video",
        "face_detector_model": "yolo_face", "face_detector_size": "640x640",
        "face_detector_margin": (0, 0, 0, 0), "face_detector_angles": [0],
        "face_detector_score": 0.5, "face_landmarker_model": "2dfan4",
        "face_landmarker_score": 0.5, "face_selector_mode": "one",
        "face_selector_order": "large-small", "face_selector_gender": None,
        "face_selector_race": None, "face_selector_age_start": None,
        "face_selector_age_end": None, "face_tracker_score": 0.0,
        "face_occluder_model": "xseg_1", "face_parser_model": "bisenet_resnet_34",
        "face_mask_types": ["box", "occlusion"], "face_mask_blur": 0.3,
        "face_mask_padding": (0, 0, 0, 0), "face_mask_areas": ["upper-face", "lower-face", "mouth"],
        "face_mask_regions": ["skin", "left-eyebrow", "right-eyebrow", "left-eye",
                              "right-eye", "glasses", "nose", "mouth", "upper-lip", "lower-lip"],
        "face_swapper_model": config["model"], "face_swapper_pixel_boost": "128x128",
        "face_swapper_weight": 0.5,
    }


class FaceFusionPipeline:
    """Calls the official lower-level API so no-face passthrough is impossible."""
    def __init__(self, config: dict[str, Any]) -> None:
        import cv2
        import numpy as np
        import onnxruntime
        from facefusion import download, metadata, state_manager

        if metadata.get("version") != SUPPORTED_VERSION:
            raise RuntimeError("FaceFusion Python 实际导入的版本不是 3.9.0；请检查安装目录和环境")
        if config["model"] not in SUPPORTED_MODELS or config["provider"] not in PROVIDER_NAMES:
            raise RuntimeError("不支持的 FaceFusion 模型或执行后端")
        provider_name = PROVIDER_NAMES[config["provider"]]
        if provider_name not in onnxruntime.get_available_providers():
            raise RuntimeError(f"FaceFusion 环境没有 {provider_name}；请安装匹配后端或在设置中明确选择 CPU")
        install_offline_download_guard(download)
        for key, value in state_defaults(config).items():
            state_manager.init_item(key, value)

        from facefusion import content_analyser
        from facefusion.face_creator import average_face_identity, get_many_faces
        from facefusion.processors.modules.face_swapper import core as swapper
        from facefusion.vision import read_static_images

        self.cv2, self.np = cv2, np
        self.config = config
        self.content_analyser = content_analyser
        self.get_many_faces = get_many_faces
        self.swapper = swapper
        # This includes the upstream content analyser; neither it nor its models
        # are disabled. Patched pre-checks only remove network and deletion actions.
        if not swapper.pre_check():
            raise RuntimeError("FaceFusion 本地模型预检失败")
        for module in [*swapper.get_common_modules(), swapper]:
            for session in module.get_inference_pool().values():
                if provider_name not in session.get_providers():
                    raise RuntimeError(f"{module.__name__} 无法启用 {provider_name}；已停止，未静默回退 CPU")
        sources = read_static_images(config["source_paths"])
        if len(sources) != len(config["source_paths"]) or any(image is None for image in sources):
            raise RuntimeError("形象图片读取失败；请使用可读取的 JPG 或 PNG")
        source_faces = []
        for image in sources:
            if content_analyser.analyse_frame(image):
                raise RuntimeError("形象图片未通过 FaceFusion 内容检查")
            faces = get_many_faces([image])
            if len(faces) != 1:
                raise RuntimeError("每张形象图片需要且只能有一张清晰人脸；请更换图片")
            source_faces.append(faces[0])
        self.source_face = average_face_identity(source_faces)
        if self.source_face is None:
            raise RuntimeError("形象图片中没有检测到可用人脸")
        self.source_image = sources[0]

    def placeholder(self, width: int, height: int, reason: str) -> Any:
        image = self.np.full((height, width, 3), 24, dtype=self.np.uint8)
        messages = {
            "no_face": "Face not visible - output paused",
            "multiple_faces": "Multiple faces - output paused",
            "unchanged_output": "Swap not confirmed - output paused",
        }
        self.cv2.putText(image, messages.get(reason, "Output paused"),
                         (12, max(28, height // 2)), self.cv2.FONT_HERSHEY_SIMPLEX,
                         min(0.65, width / 800), (225, 225, 225), 1, self.cv2.LINE_AA)
        return image

    def process(self, frame: Any) -> tuple[Any, bool, str]:
        if self.content_analyser.analyse_frame(frame):
            raise RuntimeError("摄像头画面未通过 FaceFusion 内容检查；输出已停止")
        faces = self.get_many_faces([frame])
        if len(faces) != 1:
            reason = "no_face" if not faces else "multiple_faces"
            return self.placeholder(frame.shape[1], frame.shape[0], reason), False, reason
        result = self.swapper.swap_face(self.source_face, faces[0], self.source_image, frame.copy())
        if (not isinstance(result, self.np.ndarray) or result.shape != frame.shape
                or not self.np.isfinite(result).all()):
            raise RuntimeError("FaceFusion 返回无效画面；输出已停止")
        result = self.np.clip(result, 0, 255).astype(self.np.uint8)
        if self.np.array_equal(result, frame):
            reason = "unchanged_output"
            return self.placeholder(frame.shape[1], frame.shape[0], reason), False, reason
        if self.config.get("watermark"):
            text = str(self.config["watermark"])
            if not text.isascii():
                text = "FaceSwap Studio Preview"
            self.cv2.putText(result, text[:120], (12, result.shape[0] - 16),
                             self.cv2.FONT_HERSHEY_SIMPLEX, 0.5, (245, 245, 245), 1,
                             self.cv2.LINE_AA)
        return self.np.ascontiguousarray(result), True, "swapped"


class LatestCapture:
    """Dedicated camera reader with one replaceable frame, never an input FIFO."""
    def __init__(self, config: dict[str, Any], cv2_module: Any) -> None:
        self.config, self.cv2 = config, cv2_module
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._latest = None
        self._error: Exception | None = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="camera-latest")

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        camera = None
        try:
            backend = self.cv2.CAP_DSHOW if sys.platform == "win32" else self.cv2.CAP_ANY
            camera = self.cv2.VideoCapture(self.config["camera_index"], backend)
            if not camera.isOpened():
                raise RuntimeError("摄像头无法打开；请关闭占用摄像头的应用或更换摄像头编号")
            for prop, value in ((self.cv2.CAP_PROP_FRAME_WIDTH, self.config["width"]),
                                (self.cv2.CAP_PROP_FRAME_HEIGHT, self.config["height"]),
                                (self.cv2.CAP_PROP_FPS, self.config["fps"]),
                                (self.cv2.CAP_PROP_BUFFERSIZE, 1)):
                camera.set(prop, value)
            frame_id = 0
            while not self._stop.is_set():
                ok, frame = camera.read()
                if not ok or frame is None or frame.ndim != 3 or frame.shape[2] != 3:
                    raise RuntimeError("摄像头没有返回画面或已断开；输出已停止")
                frame_id += 1
                item = (frame_id, time.time_ns(), time.monotonic_ns(), frame)
                with self._condition:
                    self._latest = item
                    self._condition.notify_all()
        except Exception as exc:  # noqa: BLE001 - camera thread reports failures to its owner
            with self._condition:
                self._error = exc
                self._latest = None
                self._condition.notify_all()
        finally:
            if camera is not None:
                camera.release()

    def take(self, timeout: float = 5) -> tuple[Any, ...]:
        with self._condition:
            if not self._condition.wait_for(
                lambda: self._latest is not None or self._error or self._stop.is_set(), timeout,
            ):
                raise RuntimeError("摄像头连续 5 秒没有新画面；输出已停止")
            if self._error:
                raise self._error
            if self._stop.is_set():
                raise RuntimeError("摄像头已停止")
            item, self._latest = self._latest, None
            return item

    def stop(self) -> None:
        self._stop.set()
        with self._condition:
            self._latest = None
            self._condition.notify_all()
        if self._thread.is_alive():
            self._thread.join(timeout=0.5)


def fit_frame(frame: Any, width: int, height: int, cv2_module: Any) -> Any:
    """Keep the camera aspect ratio; cap processing and IPC to selected dimensions."""
    scale = min(width / frame.shape[1], height / frame.shape[0])
    w, h = max(1, round(frame.shape[1] * scale)), max(1, round(frame.shape[0] * scale))
    result = cv2_module.resize(frame, (w, h))
    top, left = (height - h) // 2, (width - w) // 2
    return cv2_module.copyMakeBorder(result, top, height - h - top, left, width - w - left,
                                    cv2_module.BORDER_CONSTANT, value=(0, 0, 0))


def run(config: dict[str, Any], output: Any) -> None:
    root = Path(config["root"]).expanduser().resolve()
    if config.get("version") != SUPPORTED_VERSION:
        raise RuntimeError("此工作进程仅支持 FaceFusion 3.9.0")
    os.chdir(root)
    sys.path.insert(0, str(root))
    pipeline = FaceFusionPipeline(config)
    capture = LatestCapture(config, pipeline.cv2)
    try:
        capture.start()
        write_message(output, {"type": "ready", "engine_version": SUPPORTED_VERSION})
        previous_emit_ns = None
        while True:
            frame_id, captured_at_ns, captured_monotonic_ns, frame = capture.take()
            start_ns = time.monotonic_ns()
            frame = fit_frame(frame, config["width"], config["height"], pipeline.cv2)
            result, swapped, reason = pipeline.process(frame)
            now_ns = time.monotonic_ns()
            fps = 0.0 if previous_emit_ns is None else 1e9 / max(1, now_ns - previous_emit_ns)
            previous_emit_ns = now_ns
            meta = {
                "frame_id": frame_id, "captured_at_ns": captured_at_ns,
                "captured_monotonic_ns": captured_monotonic_ns,
                "processed_at_ns": time.time_ns(), "processed_monotonic_ns": now_ns,
                "processing_ms": (now_ns - start_ns) / 1e6,
                "capture_to_processed_ms": (now_ns - captured_monotonic_ns) / 1e6,
                "stub": False, "face_swapped": swapped, "safe_to_output": swapped,
                "placeholder": not swapped, "reason": reason, "engine_version": SUPPORTED_VERSION,
                "model": config["model"], "execution_provider": config["provider"],
            }
            write_message(output, {"type": "frame", "width": result.shape[1],
                                   "height": result.shape[0], "format": "bgr24",
                                   "fps": fps, "meta": meta}, result.tobytes())
    finally:
        capture.stop()


def main() -> int:
    # Native libraries may write directly to fd 1, bypassing sys.stdout. Reserve
    # a duplicate of the pipe and redirect both Python and native logs to stderr.
    output = os.fdopen(os.dup(sys.stdout.fileno()), "wb")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    dll_handles = []
    try:
        if sys.platform == "win32":
            # Keep conda's native runtime directory available for this process.
            # The launcher bootstrap already cleared the inherited GUI DLL path.
            for path in (Path(sys.prefix) / "Library/bin", Path(sys.prefix) / "DLLs"):
                if path.is_dir():
                    dll_handles.append(os.add_dll_directory(str(path)))
        raw = sys.stdin.buffer.readline(MAX_CONFIG_BYTES + 1)
        if not raw or len(raw) > MAX_CONFIG_BYTES:
            raise RuntimeError("缺少或超出大小限制的 FaceFusion 配置")
        config = json.loads(raw)
        if not isinstance(config, dict):
            raise TypeError("FaceFusion 配置格式无效")
        run(config, output)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - report upstream fatal_exit too
        traceback.print_exc(file=sys.stderr)
        try:
            write_message(output, {"type": "error", "message": f"{type(exc).__name__}: {exc}"[:4000]})
        except (OSError, ValueError):
            pass
        return 1
    finally:
        output.close()
        for handle in dll_handles:
            handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
