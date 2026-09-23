"""Deep-Live-Cam adapter — 即用 / simple mode (import a face image).

This module does not implement a face-swap model. It locates an upstream
Deep-Live-Cam checkout and launches it:

* ``preview`` — headless ``run.py -s <face> -t <still> -o <png>``. The shell
  displays that PNG as the first preview frame. The still is either
  ``preview_target`` or one camera grab (OpenCV only captures; DLC swaps).
* ``live`` — Deep-Live-Cam's own window via ``dlc_live_bootstrap.py``.
  Passing ``-s`` to ``run.py`` forces headless mode and skips the Live
  button, so the bootstrap pins the source after argument parsing.

``RUNNING`` means a DLC process was started. A preview frame exists only
after the headless process writes the output image. Live frames stay in
the DLC window (``read_frame()`` is ``None``), same boundary as Pro.

Not verified on NVIDIA Windows or a physical camera in this workspace.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any, NoReturn, Optional

import cv2
import numpy as np

from face_swap_studio.core.studio_settings import (
    looks_like_deeplivecam_root,
    probe_deeplivecam_root,
)
from face_swap_studio.engines.base import (
    EngineCapabilities,
    EngineConfig,
    EngineFrame,
    EngineStatus,
    FaceSwapEngine,
)
from face_swap_studio.engines.dlc_live_bootstrap import build_child_argv

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
_ALLOWED_PROCESSORS = (
    "face_swapper",
    "face_enhancer",
    "face_enhancer_gpen256",
    "face_enhancer_gpen512",
)
_ALLOWED_PROVIDERS = ("cpu", "cuda", "dml", "coreml", "rocm", "openvino", "tensorrt")
_BOOTSTRAP = Path(__file__).with_name("dlc_live_bootstrap.py")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def resolve_deeplivecam_root(explicit: Optional[str] = None) -> Optional[Path]:
    """Find a Deep-Live-Cam checkout.

    A non-empty ``explicit`` path is authoritative: a typo must not fall
    through to ``C:\\Deep-Live-Cam`` or ``DEEP_LIVE_CAM_ROOT``.
    """
    if explicit is not None and str(explicit).strip():
        root = Path(str(explicit).strip()).expanduser()
        if looks_like_deeplivecam_root(root):
            return root.resolve()
        return None
    return probe_deeplivecam_root()


def resolve_deeplivecam_python(root: Path, explicit: Optional[str] = None) -> Optional[Path]:
    """Prefer the checkout venv. Never silently use FaceSwap Studio's interpreter."""
    if explicit is not None and str(explicit).strip():
        py = Path(str(explicit).strip()).expanduser()
        return py if py.is_file() else None
    for key in ("DEEP_LIVE_CAM_PYTHON", "DLC_PYTHON"):
        env = os.environ.get(key)
        if env and Path(env).expanduser().is_file():
            return Path(env).expanduser().resolve()
    for cand in (
        root / "venv" / "Scripts" / "python.exe",
        root / "venv" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ):
        if cand.is_file():
            return cand.resolve()
    return None


def inswapper_present(root: Path) -> bool:
    models = root / "models"
    return any(
        (models / name).is_file()
        for name in ("inswapper_128.onnx", "inswapper_128_fp16.onnx")
    )


def execution_provider_from_config(config: EngineConfig) -> str:
    explicit = str(config.extra.get("execution_provider") or "").strip().lower()
    if explicit:
        provider = explicit
    else:
        gpu = (config.gpu_device or "").strip().lower()
        if gpu.startswith("cuda"):
            provider = "cuda"
        elif gpu == "cpu":
            provider = "cpu"
        elif "directml" in gpu or gpu.startswith("dml"):
            provider = "dml"
        elif "coreml" in gpu:
            provider = "coreml"
        elif "rocm" in gpu:
            provider = "rocm"
        elif "openvino" in gpu:
            provider = "openvino"
        elif "tensorrt" in gpu:
            provider = "tensorrt"
        else:
            provider = "cuda"
    if provider not in _ALLOWED_PROVIDERS:
        raise RuntimeError(
            f"不支持的 execution_provider={provider!r}。"
            f"Deep-Live-Cam 只接受：{', '.join(_ALLOWED_PROVIDERS)}。"
        )
    return provider


def frame_processors_from_extra(extra: dict[str, Any]) -> list[str]:
    raw = extra.get("frame_processors", ["face_swapper"])
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
    elif isinstance(raw, (list, tuple)):
        parts = [str(p).strip() for p in raw if str(p).strip()]
    else:
        parts = ["face_swapper"]
    if not parts:
        parts = ["face_swapper"]
    unknown = [p for p in parts if p not in _ALLOWED_PROCESSORS]
    if unknown:
        raise RuntimeError(
            f"未知 frame_processors：{unknown}。"
            f"允许：{', '.join(_ALLOWED_PROCESSORS)}。"
        )
    return parts


def validate_source_image(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"找不到即用源脸图片：{path}")
    if path.suffix.lower() not in _IMAGE_SUFFIXES:
        raise RuntimeError(
            f"源脸必须是图片（{', '.join(sorted(_IMAGE_SUFFIXES))}），当前为：{path.name}"
        )
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"无法读取源脸图片：{path}")


def capture_camera_still(
    camera_index: int,
    width: int,
    height: int,
    dest: Path,
) -> None:
    """Grab one camera frame for DLC's ``-t`` still. Does not swap faces."""
    cap = cv2.VideoCapture(camera_index)
    try:
        if not cap.isOpened():
            raise RuntimeError(
                f"打不开摄像头索引 {camera_index}，无法采集首帧目标静帧。"
            )
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        frame = None
        ok = False
        for _ in range(8):
            ok, frame = cap.read()
            if ok and frame is not None and getattr(frame, "size", 0) > 0:
                break
        if not ok or frame is None:
            raise RuntimeError(f"摄像头索引 {camera_index} 没有读到画面。")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(dest), frame):
            raise RuntimeError(f"无法写入目标静帧：{dest}")
    finally:
        cap.release()


def build_preview_command(
    python: Path,
    root: Path,
    source: Path,
    target: Path,
    output: Path,
    *,
    provider: str,
    frame_processors: list[str],
    many_faces: bool = False,
    mouth_mask: bool = False,
    execution_threads: Optional[int] = None,
    max_memory: Optional[int] = None,
) -> list[str]:
    """Upstream headless image command. This is the 选图→首帧 path."""
    cmd = [
        str(python),
        str(root / "run.py"),
        "-s",
        str(source),
        "-t",
        str(target),
        "-o",
        str(output),
        "--frame-processor",
        *frame_processors,
        "--execution-provider",
        provider,
    ]
    if many_faces:
        cmd.append("--many-faces")
    if mouth_mask:
        cmd.append("--mouth-mask")
    if execution_threads is not None:
        cmd.extend(["--execution-threads", str(int(execution_threads))])
    if max_memory is not None:
        cmd.extend(["--max-memory", str(int(max_memory))])
    return cmd


def build_live_command(
    python: Path,
    root: Path,
    source: Path,
    *,
    provider: str,
    live_mirror: bool = False,
    lang: str = "en",
    bootstrap: Path = _BOOTSTRAP,
) -> list[str]:
    """Launch the bootstrap (not ``run.py -s``). ``-s`` would skip the Live UI."""
    cmd = [
        str(python),
        str(bootstrap),
        "--dlc-root",
        str(root),
        "--source",
        str(source),
        "--execution-provider",
        provider,
        "--lang",
        lang or "en",
    ]
    if live_mirror:
        cmd.append("--live-mirror")
    # Child argv is what run.py actually sees; keep it free of -s/-t/-o.
    child = build_child_argv(
        root / "run.py",
        provider=provider,
        live_mirror=live_mirror,
        lang=lang or "en",
    )
    if any(tok in {"-s", "--source", "-t", "--target", "-o", "--output"} for tok in child):
        raise RuntimeError("内部错误：实时模式把 source 传给了 run.py，会变成 headless")
    return cmd


def _tail(path: Optional[Path], limit: int = 4000) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    data = data.strip()
    if len(data) <= limit:
        return data
    return data[-limit:]


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(value)


class DeepLiveCamEngine(FaceSwapEngine):
    def __init__(self) -> None:
        self._cfg: Optional[EngineConfig] = None
        self._status = EngineStatus.UNAVAILABLE
        self._error: Optional[str] = None
        self._note = "即用引擎未初始化"
        self._root: Optional[Path] = None
        self._python: Optional[Path] = None
        self._source: Optional[Path] = None
        self._target: Optional[Path] = None
        self._output: Optional[Path] = None
        self._session = "preview"
        self._provider = "cuda"
        self._timeout = 300.0
        self._started = 0.0
        self._proc: Optional[subprocess.Popen] = None
        self._stdout_path: Optional[Path] = None
        self._stderr_path: Optional[Path] = None
        self._stdout_fh: Optional[object] = None
        self._stderr_fh: Optional[object] = None
        self._preview_cmd: Optional[list[str]] = None
        self._live_cmd: Optional[list[str]] = None
        self._frame: Optional[np.ndarray] = None
        self._frame_meta: dict[str, Any] = {}
        self._work: Optional[Path] = None

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            name="deeplivecam",
            version="0.1.0",
            supports_live_camera=True,
            supports_gpu=True,
            notes=(
                "即用：导入脸图后调用上游 Deep-Live-Cam。"
                "首帧=run.py 静帧（-s/-t/-o）进本预览窗；"
                "实时=DLC 自己的 Live 窗口（-s 会强制 headless，故不直接传 -s）。"
                "本仓库未在 NVIDIA Windows / 物理摄像头上验收。"
            ),
            is_stub=False,
        )

    def status(self) -> EngineStatus:
        self._poll()
        return self._status

    def last_error(self) -> Optional[str]:
        return self._error

    def status_note(self) -> str:
        return self._note

    def initialize(self, config: EngineConfig) -> None:
        try:
            self.stop()
        except Exception:
            pass
        self._cfg = config
        self._error = None
        self._frame = None
        self._frame_meta = {}
        self._preview_cmd = None
        self._live_cmd = None

        session = str(config.extra.get("dlc_session") or "preview").strip().lower()
        if session not in {"preview", "live"}:
            self._fail(f"dlc_session 只能是 preview 或 live，当前为：{session}")
        self._session = session

        faces = [p for p in (config.source_face_paths or []) if str(p).strip()]
        if not faces:
            self._fail("即用模式需要至少一张源脸图片（选择脸图或导入授权素材）")
        source = Path(faces[0]).expanduser()
        try:
            validate_source_image(source)
        except RuntimeError as exc:
            self._fail(str(exc))
        self._source = source.resolve()

        explicit = config.extra.get("deeplivecam_root") or config.extra.get("dlc_root")
        explicit_s = str(explicit).strip() if explicit else ""
        root = resolve_deeplivecam_root(explicit_s or None)
        if root is None:
            if explicit_s:
                self._fail(
                    "deeplivecam_root 不是 Deep-Live-Cam 安装目录"
                    "（需要 run.py 以及 modules/core.py）："
                    f"{explicit_s}"
                )
            self._fail(
                "未找到 Deep-Live-Cam。"
                "请双击 scripts\\setup-all-win.bat 一键安装"
                "（会装到用户目录并自动写入 deeplivecam_root）。"
                "也可以设置环境变量 DEEP_LIVE_CAM_ROOT / DLC_ROOT"
                "（目录内需有 run.py 与 modules/core.py）。"
            )
        self._root = root

        py_explicit = config.extra.get("deeplivecam_python")
        py_explicit_s = str(py_explicit).strip() if py_explicit else ""
        python = resolve_deeplivecam_python(root, py_explicit_s or None)
        if python is None:
            if py_explicit_s:
                self._fail(f"deeplivecam_python 不存在：{py_explicit_s}")
            self._fail(
                "未找到 Deep-Live-Cam 的 Python。"
                f"期望 {root / 'venv' / 'Scripts' / 'python.exe'} "
                f"或 {root / 'venv' / 'bin' / 'python'}，"
                "也可设 extra.deeplivecam_python / DEEP_LIVE_CAM_PYTHON。"
                "不要改用本壳的解释器（缺少 DLC 依赖）。"
            )
        self._python = python

        try:
            provider = execution_provider_from_config(config)
            processors = frame_processors_from_extra(config.extra)
        except RuntimeError as exc:
            self._fail(str(exc))
        self._provider = provider

        threads = _optional_int(config.extra.get("execution_threads"))
        memory = _optional_int(config.extra.get("dlc_max_memory"))
        timeout = _optional_int(config.extra.get("preview_timeout_sec"))
        self._timeout = float(timeout if timeout is not None else 300)
        many = _as_bool(config.extra.get("dlc_many_faces"))
        mouth = _as_bool(config.extra.get("dlc_mouth_mask"))
        mirror = _as_bool(config.extra.get("live_mirror"))
        lang = str(config.extra.get("dlc_lang") or "en").strip() or "en"

        work = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp")
        work = work / "face-swap-studio" / "dlc"
        work.mkdir(parents=True, exist_ok=True)
        self._work = work

        model_note = ""
        if not inswapper_present(root):
            model_note = (
                " 未看到 models/inswapper_128.onnx 或 inswapper_128_fp16.onnx，"
                "DLC 首次运行会尝试自行下载。"
            )

        if session == "live":
            if not _BOOTSTRAP.is_file():
                self._fail(f"缺少实时引导脚本：{_BOOTSTRAP}")
            self._live_cmd = build_live_command(
                python,
                root,
                self._source,
                provider=provider,
                live_mirror=mirror,
                lang=lang,
            )
            self._note = (
                "即用实时：将打开 Deep-Live-Cam 窗口，源脸已预填。"
                "请在该窗口选择摄像头并点 Live。本壳不拉流。"
                "物理摄像头循环需在 Win+NVIDIA 上验收。"
                + model_note
            )
        else:
            target = self._resolve_preview_target(config, work)
            self._target = target
            self._output = work / f"first_frame_{os.getpid()}.png"
            self._preview_cmd = build_preview_command(
                python,
                root,
                self._source,
                target,
                self._output,
                provider=provider,
                frame_processors=processors,
                many_faces=many,
                mouth_mask=mouth,
                execution_threads=threads,
                max_memory=memory,
            )
            self._note = (
                "即用首帧：Deep-Live-Cam 将对源脸和一张目标静帧做官方静帧换脸，"
                "结果进本预览窗。这不是摄像头实时循环。"
                + model_note
            )

        self._status = EngineStatus.READY
        self._error = None

    def _resolve_preview_target(self, config: EngineConfig, work: Path) -> Path:
        raw = config.extra.get("preview_target") or config.extra.get("target_image") or ""
        raw_s = str(raw).strip()
        if raw_s:
            target = Path(raw_s).expanduser()
            try:
                validate_source_image(target)
            except RuntimeError as exc:
                self._fail(f"preview_target 不可用：{exc}")
            return target.resolve()
        dest = work / f"camera_still_{os.getpid()}.jpg"
        try:
            capture_camera_still(config.camera_index, config.width, config.height, dest)
        except RuntimeError as exc:
            self._fail(
                f"{exc} 也可以设置 extra.preview_target 为一张含人脸的静帧，"
                "再走 选图→首帧（不依赖摄像头）。"
            )
        return dest.resolve()

    def _fail(self, message: str) -> NoReturn:
        self._status = EngineStatus.ERROR
        self._error = message
        self._note = message
        raise RuntimeError(message)

    def start(self) -> None:
        if self._status not in (EngineStatus.READY, EngineStatus.RUNNING):
            raise RuntimeError(self._error or "即用引擎未就绪")
        if self._proc is not None and self._proc.poll() is None:
            self._status = EngineStatus.RUNNING
            return
        assert self._root is not None and self._python is not None
        if self._session == "live":
            cmd = self._live_cmd
        else:
            cmd = self._preview_cmd
            if self._output is not None and self._output.exists():
                self._output.unlink()
            self._frame = None
        if not cmd:
            raise RuntimeError(self._error or "没有可执行的 Deep-Live-Cam 命令")
        self._open_logs()
        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(self._root),
                env=_child_env(),
                stdout=self._stdout_fh,  # type: ignore[arg-type]
                stderr=self._stderr_fh,  # type: ignore[arg-type]
            )
        except OSError as exc:
            self._status = EngineStatus.ERROR
            self._error = f"无法启动 Deep-Live-Cam：{exc}；cmd={cmd}"
            self._note = self._error
            self._close_logs()
            raise RuntimeError(self._error) from exc
        self._started = time.monotonic()
        self._status = EngineStatus.RUNNING
        if self._session == "preview":
            self._note = (
                "Deep-Live-Cam 正在生成首帧（加载 inswapper 可能要数分钟）。"
                "RUNNING 还不是出画。"
            )
        else:
            self._note = (
                "Deep-Live-Cam 窗口已启动。源脸已预填；请在 DLC 窗口点 Live。"
                "本壳 read_frame() 为 None（画面在 DLC 窗口）。"
                "未在本机 NVIDIA/摄像头上验证。"
            )

    def _open_logs(self) -> None:
        self._close_logs()
        assert self._work is not None
        self._stdout_path = self._work / f"dlc_{self._session}_stdout.log"
        self._stderr_path = self._work / f"dlc_{self._session}_stderr.log"
        self._stdout_fh = open(self._stdout_path, "w", encoding="utf-8", errors="replace")
        self._stderr_fh = open(self._stderr_path, "w", encoding="utf-8", errors="replace")

    def _close_logs(self) -> None:
        for fh in (self._stdout_fh, self._stderr_fh):
            if fh is not None:
                try:
                    fh.close()
                except OSError:
                    pass
        self._stdout_fh = None
        self._stderr_fh = None

    def _poll(self) -> None:
        proc = self._proc
        if proc is None:
            return
        code = proc.poll()
        if code is None:
            if (
                self._session == "preview"
                and self._frame is None
                and self._started
                and (time.monotonic() - self._started) > self._timeout
            ):
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                self._proc = None
                self._close_logs()
                self._status = EngineStatus.ERROR
                self._error = (
                    f"Deep-Live-Cam 首帧超时（>{int(self._timeout)}s）。"
                    f"日志：{self._stderr_path}\n{_tail(self._stderr_path)}\n{_tail(self._stdout_path)}"
                )
                self._note = self._error
            return
        self._proc = None
        self._close_logs()
        if self._session == "live":
            if code != 0:
                self._status = EngineStatus.ERROR
                self._error = (
                    f"Deep-Live-Cam 进程退出 code={code}。"
                    f"\n{_tail(self._stderr_path)}"
                )
                self._note = self._error
            elif self._status == EngineStatus.RUNNING:
                self._status = EngineStatus.READY
                self._note = "Deep-Live-Cam 窗口已关闭。"
            return
        self._finish_preview(code)

    def _finish_preview(self, code: int) -> None:
        output = self._output
        err_tail = _tail(self._stderr_path)
        out_tail = _tail(self._stdout_path)
        log_bits = "\n".join(bit for bit in (out_tail, err_tail) if bit)
        if output is None or not output.is_file() or output.stat().st_size <= 0:
            self._status = EngineStatus.ERROR
            self._error = (
                f"Deep-Live-Cam 未写出首帧（exit={code}）。"
                "常见原因：PATH 上没有 ffmpeg、execution-provider 不可用"
                "（NVIDIA 包才有 cuda）、源图或目标静帧没有脸、模型未下完。"
                f"\n日志：{self._stderr_path}\n{log_bits}"
            )
            self._note = self._error
            return
        image = cv2.imread(str(output), cv2.IMREAD_COLOR)
        if image is None:
            self._status = EngineStatus.ERROR
            self._error = f"首帧文件无法读取：{output}\n{log_bits}"
            self._note = self._error
            return
        if code not in (0, None):
            self._status = EngineStatus.ERROR
            self._error = (
                f"Deep-Live-Cam 退出 code={code}，忽略不完整输出。\n{log_bits}"
            )
            self._note = self._error
            return
        if self._cfg and self._cfg.watermark_text:
            cv2.putText(
                image,
                self._cfg.watermark_text,
                (16, max(image.shape[0] - 16, 24)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
        self._frame = image
        self._frame_meta = {
            "engine": "deeplivecam",
            "kind": "first_frame",
            "live_camera_loop": False,
            "hardware_verified": False,
            "source": str(self._source) if self._source else "",
            "target": str(self._target) if self._target else "",
            "output": str(output),
            "execution_provider": self._provider,
        }
        self._status = EngineStatus.RUNNING
        self._note = (
            "即用首帧已写入预览（Deep-Live-Cam 静帧管线）。"
            "这不是摄像头实时循环；实时请把输出改为「DLC 实时窗口」。"
            "未在本机 NVIDIA/摄像头上验证。"
        )

    def stop(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
        self._close_logs()
        if self._status == EngineStatus.RUNNING:
            self._status = EngineStatus.READY
            if self._frame is not None:
                self._note = "已停止。首帧仍可从上次输出文件查看。"

    def set_source_faces(self, paths: list[str]) -> None:
        if self._cfg is not None:
            self._cfg.source_face_paths = list(paths)

    def read_frame(self) -> Optional[EngineFrame]:
        self._poll()
        if self._frame is None:
            return None
        return EngineFrame(image=self._frame.copy(), fps=0.0, meta=dict(self._frame_meta))

    def shutdown(self) -> None:
        try:
            self.stop()
        except Exception:
            pass


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    return env
