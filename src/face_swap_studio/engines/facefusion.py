"""Real local FaceFusion 3.9.0 adapter using an isolated external interpreter.

READY means configured, STARTING means loading, and RUNNING requires a swapped
frame. start/read_frame/stop never wait for model, camera or process operations.
"""
from __future__ import annotations

import ast
import copy
import json
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from .base import EngineCapabilities, EngineConfig, EngineFrame, EngineStatus, FaceSwapEngine
from .facefusion_protocol import MAX_CONFIG_BYTES, ProtocolError, read_message

SUPPORTED_VERSION = "3.9.0"
SUPPORTED_MODELS = ("inswapper_128", "inswapper_128_fp16")
SUPPORTED_PROVIDERS = ("cuda", "cpu", "directml", "coreml")
MAX_OUTPUT_AGE_NS = 2_000_000_000


def resolve_facefusion_root(explicit: str | Path | None = None) -> Path | None:
    """An explicit path never silently falls back to another installation."""
    selected = explicit or os.environ.get("FACEFUSION_ROOT")
    candidates = [Path(selected)] if selected else [
        Path.home() / "facefusion", Path.home() / "FaceFusion", Path("C:/facefusion"),
    ]
    for path in candidates:
        path = path.expanduser()
        if (path / "facefusion.py").is_file() and (path / "facefusion/metadata.py").is_file():
            return path.resolve()
    return None


def read_facefusion_version(root: Path) -> str:
    """Read metadata without executing installation code in the app process."""
    path = root / "facefusion/metadata.py"
    if path.stat().st_size > 65536:
        raise ValueError("FaceFusion metadata.py 过大，无法识别版本")
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "METADATA" for target in node.targets
        ):
            metadata = ast.literal_eval(node.value)
            if isinstance(metadata, dict) and isinstance(metadata.get("version"), str):
                return metadata["version"]
    raise ValueError("无法识别 FaceFusion 版本；需要官方 3.9.0 安装目录")


def resolve_facefusion_python(root: Path, explicit: str | Path | None = None) -> Path | None:
    selected = explicit or os.environ.get("FACEFUSION_PYTHON")
    if selected:
        path = Path(selected).expanduser()
        # Preserve venv symlinks: resolve() would switch to the base environment.
        return path.absolute() if path.is_file() else None
    candidates = [
        root / ".venv/Scripts/python.exe", root / "venv/Scripts/python.exe",
        root / ".venv/bin/python", root / "venv/bin/python",
        root / "python/python.exe", root / "_internal/python/python.exe",
        root / "conda/envs/facefusion/python.exe",
    ]
    for base in (Path.home() / "miniconda3", Path.home() / "anaconda3",
                 Path.home() / "miniforge3"):
        candidates.extend([base / "envs/facefusion/python.exe", base / "envs/facefusion/bin/python"])
    return next((path.absolute() for path in candidates if path.is_file()), None)


def _worker_env(python: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "__PYVENV_LAUNCHER__"):
        env.pop(key, None)
    for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        env.pop(key, None)
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        anchor = os.path.normcase(os.path.abspath(bundle))
        for key in ("PATH", "DYLD_LIBRARY_PATH"):
            env[key] = os.pathsep.join(
                part for part in env.get(key, "").split(os.pathsep)
                if part and not (
                    os.path.normcase(os.path.abspath(part)) == anchor
                    or os.path.normcase(os.path.abspath(part)).startswith(anchor + os.sep)
                )
            )
        if "LD_LIBRARY_PATH_ORIG" in env:
            env["LD_LIBRARY_PATH"] = env["LD_LIBRARY_PATH_ORIG"]
        else:
            env.pop("LD_LIBRARY_PATH", None)
    env.update(PYTHONNOUSERSITE="1", PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    prefix = python.parent
    if prefix.name.lower() in {"scripts", "bin"}:
        prefix = prefix.parent
    paths = [python.parent, prefix, prefix / "Library/bin", prefix / "Scripts"]
    env["PATH"] = os.pathsep.join(str(p) for p in paths if p.is_dir()) + os.pathsep + env.get("PATH", "")
    return env


class FaceFusionEngine(FaceSwapEngine):
    def __init__(self, facefusion_root: Path | None = None) -> None:
        self._root_hint = facefusion_root
        self._root: Path | None = None
        self._python: Path | None = None
        self._cfg: EngineConfig | None = None
        self._worker_config: dict[str, Any] | None = None
        self._status = EngineStatus.UNAVAILABLE
        self._error: str | None = None
        self._latest: EngineFrame | None = None
        self._proc: subprocess.Popen | None = None
        self._lock = threading.RLock()
        self._generation = 0
        self._stop_event = threading.Event()
        self._started_at = self._received_at = 0.0
        self._ready = False
        self._startup_timeout = 120.0
        self._stderr_tail = ""
        self._last_frame_id = 0

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            name="facefusion", version=f"adapter-1 / FaceFusion {SUPPORTED_VERSION}",
            supports_live_camera=True, supports_gpu=True, is_stub=False,
            notes="本地独立进程真实照片换脸；需官方 FaceFusion 3.9.0 及现有模型。画质和速度需真机验证。",
        )

    def initialize(self, config: EngineConfig) -> None:
        self.stop()
        with self._lock:
            self._cfg = self._worker_config = None
            self._status, self._error = EngineStatus.ERROR, None
        try:
            cfg = copy.deepcopy(config)
            if not cfg.source_face_paths:
                raise ValueError("照片模式需要至少一张形象图片")
            if len(cfg.source_face_paths) > 8:
                raise ValueError("此版本最多支持 8 张同一人的形象图片")
            sources = []
            for raw in cfg.source_face_paths:
                path = Path(raw).expanduser().resolve()
                if not path.is_file():
                    raise ValueError(f"找不到形象图片：{path}")
                sources.append(str(path))
            if cfg.camera_index < 0 or not 160 <= cfg.width <= 1920 or not 120 <= cfg.height <= 1080:
                raise ValueError("摄像头编号或画面尺寸无效（支持 160×120 至 1920×1080）")
            root = resolve_facefusion_root(cfg.extra.get("facefusion_root") or self._root_hint)
            if root is None:
                raise ValueError("找不到 FaceFusion；请在高级设置选择含 facefusion.py 的官方 3.9.0 目录")
            version = read_facefusion_version(root)
            if version != SUPPORTED_VERSION:
                raise ValueError(f"此适配器支持 FaceFusion {SUPPORTED_VERSION}，检测到 {version}；请使用匹配版本")
            python = resolve_facefusion_python(root, cfg.extra.get("facefusion_python"))
            if python is None:
                raise ValueError("找不到 FaceFusion 专用 Python；请在高级设置选择该环境的 python.exe / python")
            model = str(cfg.extra.get("facefusion_model") or "inswapper_128")
            if model not in SUPPORTED_MODELS:
                raise ValueError("此版本支持 inswapper_128 或 inswapper_128_fp16；请更换模型设置")
            provider = str(cfg.extra.get("facefusion_execution_provider") or cfg.gpu_device.split(":")[0])
            if provider not in SUPPORTED_PROVIDERS:
                raise ValueError(f"暂不支持执行后端 {provider}；可选 cuda / cpu / directml / coreml")
            device_id = int(cfg.gpu_device.split(":", 1)[1]) if ":" in cfg.gpu_device else 0
            if device_id < 0:
                raise ValueError("GPU 编号不能为负数")
            timeout = float(cfg.extra.get("facefusion_startup_timeout") or 120)
            if not math.isfinite(timeout) or not 10 <= timeout <= 600:
                raise ValueError("引擎启动等待时间必须为 10 至 600 秒")
            worker_config = {
                "root": str(root), "version": version, "source_paths": sources,
                "camera_index": cfg.camera_index, "width": cfg.width, "height": cfg.height,
                "model": model, "provider": provider, "device_id": device_id,
                "fps": 30, "watermark": cfg.watermark_text,
            }
            if len(json.dumps(worker_config).encode("utf-8")) > MAX_CONFIG_BYTES:
                raise ValueError("FaceFusion 配置过大")
        except Exception as exc:
            with self._lock:
                self._error = str(exc)
            raise RuntimeError(str(exc)) from exc
        with self._lock:
            self._root, self._python, self._cfg = root, python, cfg
            self._worker_config, self._startup_timeout = worker_config, timeout
            self._status = EngineStatus.READY

    def start(self) -> None:
        with self._lock:
            if self._status in {EngineStatus.STARTING, EngineStatus.RUNNING}:
                return
            if self._status != EngineStatus.READY or self._worker_config is None:
                raise RuntimeError(self._error or "照片引擎尚未配置完成")
            self._generation += 1
            generation = self._generation
            self._stop_event = threading.Event()
            self._latest, self._last_frame_id, self._error = None, 0, None
            self._stderr_tail, self._ready = "", False
            self._started_at, self._received_at = time.monotonic(), 0.0
            self._status = EngineStatus.STARTING
            for target, name in ((self._run_worker, "reader"), (self._watchdog, "watchdog")):
                threading.Thread(target=target, args=(generation, self._stop_event),
                                 daemon=True, name=f"facefusion-{name}").start()

    def _launch_command(self) -> list[str]:
        worker = str(Path(__file__).with_name("facefusion_worker.py"))
        if sys.platform == "win32":
            # PyInstaller's SetDllDirectory setting is inherited by child processes.
            # Reset it in the *child* before importing native numerical libraries;
            # changing it in the GUI process would race Qt/native plugin loading.
            bootstrap = (
                "import ctypes, sys; "
                "ctypes.windll.kernel32.SetDllDirectoryW(None); "
                "import os, runpy; "
                "sys.path.insert(0, os.path.dirname(sys.argv[1])); "
                "runpy.run_path(sys.argv[1], run_name='__main__')"
            )
            return [str(self._python), "-u", "-c", bootstrap, worker]
        return [str(self._python), "-u", worker]

    def _run_worker(self, generation: int, stop_event: threading.Event) -> None:
        proc = None
        try:
            with self._lock:
                if generation != self._generation or stop_event.is_set():
                    return
                command, root, python = self._launch_command(), self._root, self._python
                config = json.dumps(self._worker_config).encode("utf-8") + b"\n"
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            proc = subprocess.Popen(command, cwd=str(root), env=_worker_env(python),
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, creationflags=flags)
            with self._lock:
                if generation != self._generation or stop_event.is_set():
                    return
                self._proc = proc
            threading.Thread(target=self._drain_stderr, args=(proc, generation),
                             daemon=True, name="facefusion-stderr").start()
            proc.stdin.write(config)
            proc.stdin.flush()
            proc.stdin.close()
            while not stop_event.is_set():
                message = read_message(proc.stdout)
                if message is None:
                    break
                self._accept_message(generation, *message)
            if not stop_event.is_set():
                self._fail(generation, f"FaceFusion 工作进程退出（代码 {proc.poll()}）；请检查专用 Python、模型及显卡环境")
        except Exception as exc:  # noqa: BLE001 - translate thread failures to GUI state
            if not stop_event.is_set():
                self._fail(generation, f"FaceFusion 无法运行：{exc}")
        finally:
            if proc is not None:
                self._reap(proc)

    def _drain_stderr(self, proc: subprocess.Popen, generation: int) -> None:
        try:
            while True:
                chunk = proc.stderr.read(1024)
                if not chunk:
                    break
                with self._lock:
                    if generation == self._generation:
                        self._stderr_tail = (self._stderr_tail + chunk.decode("utf-8", "replace"))[-8192:]
        except (OSError, ValueError):
            pass

    def _accept_message(self, generation: int, header: dict[str, Any], payload: bytes) -> None:
        with self._lock:
            if generation != self._generation or self._stop_event.is_set():
                return
            if header["type"] == "error":
                self._fail(generation, str(header.get("message") or "FaceFusion 处理失败"))
                return
            if header["type"] == "ready":
                if header.get("engine_version") != SUPPORTED_VERSION:
                    raise ProtocolError("Worker reported an unexpected FaceFusion version")
                self._ready, self._received_at = True, time.monotonic()
                return
            if not self._ready:
                raise ProtocolError("Worker emitted a frame before model validation")
            meta = dict(header["meta"])
            frame_id = meta.get("frame_id")
            if type(frame_id) is not int or frame_id <= self._last_frame_id:
                raise ProtocolError("Worker emitted an invalid or out-of-order frame ID")
            if meta.get("engine_version") != SUPPORTED_VERSION:
                raise ProtocolError("Frame engine version mismatch")
            for key in ("captured_at_ns", "captured_monotonic_ns", "processed_at_ns",
                        "processed_monotonic_ns"):
                if type(meta.get(key)) is not int or meta[key] <= 0:
                    raise ProtocolError("Worker omitted frame timing")
            if not (
                meta["captured_monotonic_ns"] <= meta["processed_monotonic_ns"]
                <= time.monotonic_ns()
            ):
                raise ProtocolError("Worker returned future or reversed monotonic frame timing")
            swapped = meta.get("face_swapped") is True and meta.get("safe_to_output") is True
            if not swapped and meta.get("placeholder") is not True:
                raise ProtocolError("Worker returned an unsafe camera passthrough frame")
            image = np.frombuffer(payload, dtype=np.uint8).reshape(header["height"], header["width"], 3).copy()
            meta.update(stub=False, face_swapped=swapped, safe_to_output=swapped,
                        received_at_ns=time.time_ns())
            fps = float(header.get("fps", 0.0))
            if not math.isfinite(fps) or fps < 0:
                raise ProtocolError("Invalid worker FPS")
            self._latest = EngineFrame(image=image, fps=fps, meta=meta)
            self._last_frame_id, self._received_at = frame_id, time.monotonic()
            if swapped:
                self._status = EngineStatus.RUNNING

    def _watchdog(self, generation: int, stop_event: threading.Event) -> None:
        while not stop_event.wait(0.2):
            with self._lock:
                if generation != self._generation:
                    return
                now = time.monotonic()
                if not self._ready and now - self._started_at > self._startup_timeout:
                    self._fail(generation, "FaceFusion 加载超时；请检查模型、专用 Python 或增加启动等待时间")
                elif self._ready and now - self._received_at > 15:
                    self._fail(generation, "FaceFusion 连续 15 秒没有新画面；摄像头或推理已停止，请重新启动")

    def _fail(self, generation: int, message: str) -> None:
        with self._lock:
            if generation != self._generation or self._stop_event.is_set():
                return
            self._status, self._error = EngineStatus.ERROR, message[:4096]
            self._latest = None
            self._stop_event.set()
            if self._proc is not None:
                self._request_termination(self._proc)

    def status(self) -> EngineStatus:
        with self._lock:
            return self._status

    def read_frame(self) -> EngineFrame | None:
        with self._lock:
            frame, self._latest = self._latest, None
        if frame is not None and frame.meta.get("safe_to_output") is True:
            age = time.monotonic_ns() - frame.meta["captured_monotonic_ns"]
            if age > MAX_OUTPUT_AGE_NS or age < 0:
                # A stalled worker/UI must never revive an old eligible frame.
                # This is a generous stale-frame cutoff, not a latency promise.
                frame = EngineFrame(
                    image=np.full_like(frame.image, 24), fps=frame.fps,
                    meta={**frame.meta, "face_swapped": False, "safe_to_output": False,
                          "placeholder": True, "reason": "stale_frame"},
                )
        return frame

    def last_error(self) -> str | None:
        with self._lock:
            return self._error

    def diagnostic_tail(self) -> str:
        """Bounded local diagnostic text; redact before sharing outside the device."""
        with self._lock:
            return self._stderr_tail

    @staticmethod
    def _request_termination(proc: subprocess.Popen) -> None:
        """Kill a stuck worker even when its stdout reader is blocked."""
        try:
            proc.terminate()
        except OSError:
            pass

        def escalate() -> None:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass
            except OSError:
                pass

        threading.Thread(target=escalate, daemon=True, name="facefusion-reaper").start()

    @staticmethod
    def _reap(proc: subprocess.Popen) -> None:
        try:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass

    def stop(self) -> None:
        with self._lock:
            self._generation += 1
            self._stop_event.set()
            proc, self._proc = self._proc, None
            self._latest, self._ready = None, False
            self._status = EngineStatus.READY if self._worker_config is not None else EngineStatus.UNAVAILABLE
        if proc is not None:
            self._request_termination(proc)
            # Reader owns wait/kill/close, outside the GUI thread.

    def set_source_faces(self, paths: list[str]) -> None:
        with self._lock:
            if self._cfg is None:
                return
            cfg = copy.deepcopy(self._cfg)
        cfg.source_face_paths = list(paths)
        self.initialize(cfg)

    def shutdown(self) -> None:
        self.stop()


def create_facefusion_engine(root: str | None = None) -> FaceSwapEngine:
    return FaceFusionEngine(Path(root) if root else None)
