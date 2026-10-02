"""DFM adapter for a headless worker in an installed DeepFaceLive NVIDIA runtime.

Legacy launcher helpers remain available for setup diagnostics only; the Pro
engine never calls them or opens the upstream GUI.
"""

from __future__ import annotations

import copy
import math
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from face_swap_studio.engines.base import (
    EngineCapabilities,
    EngineConfig,
    EngineStatus,
    FaceSwapEngine,
)

from .facefusion import IsolatedWorkerEngine, _worker_env

_LAUNCHERS = (
    "DeepFaceLive.bat",
    "DeepFaceLive.cmd",
    "main.py",
)

_MIN_DFM_BYTES = 512 * 1024

_CUDA_NAME_PREFIXES = ("cudnn", "cublas", "cudart", "cufile", "cufft", "curand", "cusolver", "cusparse")
_CUDA_NAME_TOKENS = ("nvinfer", "nvrtc", "nvcuda")


@dataclass(frozen=True)
class BuildInfo:
    kind: str  # "nvidia" | "dx12" | "unknown"
    evidence: str
    provider: str = "unknown"  # cuda | directml | unknown


@dataclass(frozen=True)
class DfmCheck:
    ok: bool
    message: str
    size_bytes: int = 0


def resolve_deepfacelive_root(explicit: str | None = None) -> Path | None:
    """Find DeepFaceLive install directory (NVIDIA paths preferred in order)."""
    selected = explicit or os.environ.get("DEEPFACELIVE_ROOT") or os.environ.get("DFL_ROOT")
    candidates = [Path(selected)] if selected else [
        Path("C:/DeepFaceLive_NVIDIA"), Path.home() / "DeepFaceLive_NVIDIA",
        Path("C:/DeepFaceLive"), Path.home() / "DeepFaceLive",
    ]
    for root in candidates:
        if not root:
            continue
        root = root.expanduser()
        if _looks_like_dfl_root(root):
            return root.resolve()
    return None


def _looks_like_dfl_root(root: Path) -> bool:
    if any((root / name).exists() for name in _LAUNCHERS):
        return True
    # Official portable: launcher may sit beside _internal only
    if (root / "_internal" / "DeepFaceLive" / "main.py").is_file():
        return True
    return bool((root / "_internal" / "python" / "python.exe").is_file() and (root / "DeepFaceLive.bat").is_file())


def _iter_scan_files(root: Path, *, max_files: int = 400) -> list[Path]:
    """Collect files from root + official CUDA / site-packages hotspots."""
    out: list[Path] = []
    hotspots = [
        root,
        root / "_internal" / "CUDA",
        root / "_internal" / "CUDA" / "bin",
        root / "_internal" / "python" / "Lib" / "site-packages",
        root / "_internal" / "DeepFaceLive",
    ]
    seen: set[Path] = set()
    for base in hotspots:
        if not base.exists() or base in seen:
            continue
        seen.add(base)
        try:
            if base.is_file():
                out.append(base)
                continue
            for dirpath, dirnames, filenames in os.walk(base):
                # Keep walk shallow-ish under site-packages
                depth = Path(dirpath).relative_to(base).parts
                if len(depth) > 3 and "CUDA" not in str(base):
                    dirnames[:] = []
                for name in filenames:
                    out.append(Path(dirpath) / name)
                    if len(out) >= max_files:
                        return out
        except OSError:
            continue
    return out


def _is_cuda_dll_name(name: str) -> bool:
    n = name.lower()
    if not n.endswith(".dll"):
        return False
    if any(n.startswith(p) for p in _CUDA_NAME_PREFIXES):
        return True
    return any(tok in n for tok in _CUDA_NAME_TOKENS)


def _is_dx_dll_name(name: str) -> bool:
    n = name.lower()
    return "d3d12" in n or n.endswith("_dx12.dll") or "directml" in n


def detect_build_kind(root: Path) -> BuildInfo:
    """Classify NVIDIA vs DX12 using official portable layout (_internal/CUDA/bin)."""
    name = root.name.lower()
    files = _iter_scan_files(root)
    file_names = [p.name.lower() for p in files]
    rel_bits = []
    for p in files[:120]:
        try:
            rel_bits.append(str(p.relative_to(root)).lower())
        except ValueError:
            rel_bits.append(p.name.lower())
    rel_hints = " ".join(rel_bits)

    nvidia_hits: list[str] = []
    dx_hits: list[str] = []
    provider = "unknown"

    if "nvidia" in name or "cuda" in name:
        nvidia_hits.append(f"路径含 NVIDIA/CUDA：{root.name}")
    if "dx12" in name or "directx" in name or "directml" in name:
        dx_hits.append(f"路径含 DX12/DirectX/DirectML：{root.name}")

    cuda_bin = root / "_internal" / "CUDA" / "bin"
    if cuda_bin.is_dir():
        cuda_dlls = [p.name for p in cuda_bin.iterdir() if p.is_file() and _is_cuda_dll_name(p.name)]
        if cuda_dlls:
            nvidia_hits.append(
                f"_internal/CUDA/bin 含 CUDA DLL：{', '.join(sorted(cuda_dlls)[:4])}"
            )
            provider = "cuda"

    root_cuda = [n for n in file_names if _is_cuda_dll_name(n)]
    if root_cuda and not any("_internal/cuda" in h.lower() for h in nvidia_hits):
        nvidia_hits.append(f"发现 CUDA 相关文件：{', '.join(root_cuda[:4])}")
        provider = "cuda"

    if "onnxruntime_gpu" in rel_hints or "onnxruntime-gpu" in rel_hints:
        nvidia_hits.append("site-packages 含 onnxruntime-gpu")
        provider = "cuda"
    if "onnxruntime_directml" in rel_hints or "onnxruntime-directml" in rel_hints:
        dx_hits.append("site-packages 含 onnxruntime-directml")
        if provider == "unknown":
            provider = "directml"

    dx_dlls = [n for n in file_names if _is_dx_dll_name(n)]
    if dx_dlls:
        dx_hits.append(f"发现 DX12/DirectML 相关文件：{', '.join(dx_dlls[:4])}")
        if provider == "unknown":
            provider = "directml"

    if nvidia_hits and not dx_hits:
        return BuildInfo("nvidia", "; ".join(nvidia_hits), provider or "cuda")
    if dx_hits and not nvidia_hits:
        return BuildInfo("dx12", "; ".join(dx_hits), provider or "directml")
    if nvidia_hits and dx_hits:
        if provider == "cuda" or any("CUDA/bin" in h for h in nvidia_hits):
            return BuildInfo("nvidia", "; ".join(nvidia_hits + dx_hits), "cuda")
        return BuildInfo("dx12", "; ".join(dx_hits + nvidia_hits), provider)
    return BuildInfo(
        "unknown",
        "未在根目录或 _internal/CUDA/bin 检测到明确的 NVIDIA/CUDA 或 DX12 标记"
        "（官方 NVIDIA 便携包改名 DeepFaceLive 时仍应能通过 _internal/CUDA/bin 识别）",
        "unknown",
    )


def validate_dfm_file(
    path: Path,
    *,
    expected_hint: str | None = None,
) -> DfmCheck:
    if not path.is_file():
        return DfmCheck(False, f"找不到 .dfm 文件：{path}")
    if path.suffix.lower() != ".dfm":
        return DfmCheck(False, f"扩展名必须是 .dfm，当前为：{path.suffix}")

    size = path.stat().st_size
    if size < _MIN_DFM_BYTES:
        return DfmCheck(
            False,
            f".dfm 过小（{size} 字节），更像损坏或占位文件；真实专模通常 ≥ {_MIN_DFM_BYTES // 1024}KB。"
            f"请重新从 DeepFaceLab 导出，并确认与当前 DeepFaceLive 版本匹配。",
            size,
        )

    with path.open("rb") as stream:
        head = stream.read(4096)
    looks_onnx = (b"onnx" in head.lower()) or head.startswith(b"\x08")
    if not looks_onnx:
        return DfmCheck(
            False,
            f".dfm 未通过格式预检（未见 ONNX/模型指纹）：{path.name}。"
            "常见原因：①文件损坏或下到一半；②不是 DeepFaceLive 用的专模；"
            "③用错版本的 DeepFaceLab 导出。请用与本机 DeepFaceLive 同代的 DFL 重新导出 .dfm。",
            size,
        )

    sidecar = path.with_suffix(path.suffix + ".version")
    if not sidecar.is_file():
        sidecar = path.with_suffix(".version")
    hint = (expected_hint or "").strip()
    if not hint and sidecar.is_file():
        hint = sidecar.read_text(encoding="utf-8", errors="ignore").strip()

    if hint:
        stem = path.stem.lower()
        if hint.lower() not in stem and hint.lower() not in path.name.lower() and not (
            sidecar.is_file()
            and sidecar.read_text(encoding="utf-8", errors="ignore").strip() == hint
        ):
            return DfmCheck(
                False,
                f".dfm 版本提示不匹配：期望「{hint}」，文件名为「{path.name}」。"
                "DeepFaceLive 加载失败时多数是「导出 DFL 版本 ≠ 本机 DFL 版本」。"
                "请用同一代 DeepFaceLab 重新导出，或更换匹配的 DeepFaceLive NVIDIA 包。",
                size,
            )

    return DfmCheck(True, "ok", size)


def _userdata_dir(root: Path, override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    ud = root / "userdata"
    ud.mkdir(parents=True, exist_ok=True)
    return ud


def stage_dfm(dfm_path: Path, userdata: Path) -> Path:
    models = userdata / "dfm_models"
    models.mkdir(parents=True, exist_ok=True)
    dest = models / dfm_path.name
    if dest.resolve() != dfm_path.resolve():
        shutil.copy2(dfm_path, dest)
    return dest


def _official_python(root: Path) -> Path | None:
    for cand in (
        root / "_internal" / "python" / "python.exe",
        root / "_internal" / "python" / "python",
        root / "python.exe",
    ):
        if cand.is_file():
            return cand
    return None


def _official_main_py(root: Path) -> Path | None:
    for cand in (
        root / "_internal" / "DeepFaceLive" / "main.py",
        root / "DeepFaceLive" / "main.py",
        root / "main.py",
    ):
        if cand.is_file():
            return cand
    return None


def build_launch_command(
    root: Path,
    userdata: Path,
    *,
    no_cuda: bool = False,
) -> list[str]:
    """Build argv. Prefer python+--userdata-dir when userdata ≠ <root>/userdata.

    Official DeepFaceLive.bat hardcodes %~dp0userdata and would ignore custom dirs.
    """
    default_ud = (root / "userdata").resolve()
    custom_ud = userdata.resolve() != default_ud
    py = _official_python(root)
    main_py = _official_main_py(root)

    # Custom userdata OR missing bat → python entry with explicit --userdata-dir
    if custom_ud or no_cuda or not (root / "DeepFaceLive.bat").is_file():
        if py is None:
            py_cmd = sys.executable
        else:
            py_cmd = str(py)
        if main_py is None:
            raise FileNotFoundError(
                f"未找到 DeepFaceLive main.py（需要 _internal/DeepFaceLive/main.py 或根目录 main.py）：{root}"
            )
        cmd = [
            py_cmd,
            str(main_py),
            "run",
            "DeepFaceLive",
            "--userdata-dir",
            str(userdata),
        ]
        if no_cuda:
            cmd.append("--no-cuda")
        return cmd

    # Default userdata on Win: bat is OK (official embeds %~dp0userdata)
    bat = root / "DeepFaceLive.bat"
    if sys.platform == "win32" and bat.is_file():
        return [str(bat)]
    cmd_file = root / "DeepFaceLive.cmd"
    if sys.platform == "win32" and cmd_file.is_file():
        return [str(cmd_file)]

    # Fallback python
    if main_py is None:
        raise FileNotFoundError(f"未找到 DeepFaceLive 入口: {root}")
    py_cmd = str(py) if py else sys.executable
    cmd = [py_cmd, str(main_py), "run", "DeepFaceLive", "--userdata-dir", str(userdata)]
    if no_cuda:
        cmd.append("--no-cuda")
    return cmd


def launch_env(root: Path) -> dict[str, str]:
    """Augment PATH/CUDA_PATH for official portable packs."""
    env = {**os.environ}
    cuda = root / "_internal" / "CUDA"
    cuda_bin = cuda / "bin"
    py_dir = root / "_internal" / "python"
    ffmpeg = root / "_internal" / "ffmpeg"
    parts: list[str] = []
    for p in (cuda_bin, cuda, py_dir, py_dir / "Scripts", ffmpeg):
        if p.is_dir():
            parts.append(str(p))
    if parts:
        env["PATH"] = os.pathsep.join(parts + [env.get("PATH", "")])
    if cuda.is_dir():
        env["CUDA_PATH"] = str(cuda)
        env["CUDA_BIN_PATH"] = str(cuda_bin)
    if py_dir.is_dir():
        env["PYTHON_PATH"] = str(py_dir)
        env["PYTHONEXECUTABLE"] = str(py_dir / "python.exe")
    return env


class DeepFaceLiveEngine(IsolatedWorkerEngine):
    """Run DFM inference in a hidden worker; the application owns all UI."""

    worker_filename = "deepfacelive_worker.py"
    engine_version = "dfl-headless-1"
    display_name = "专用模型引擎"

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            name="deepfacelive", version=self.engine_version,
            supports_live_camera=True, supports_gpu=True, is_stub=False,
            preview_mode="internal",
            notes="本机 DFM 推理与实时预览；需 NVIDIA 便携引擎。效果与速度需真机验收。",
        )

    def initialize(self, config: EngineConfig) -> None:
        self.stop()
        with self._lock:
            self._cfg = self._worker_config = None
            self._status, self._error = EngineStatus.ERROR, None
        try:
            cfg = copy.deepcopy(config)
            raw = str(cfg.extra.get("dfm_path") or "").strip()
            if not raw:
                raise ValueError("请选择已经导出的 .dfm 专用模型")
            dfm = Path(raw).expanduser().resolve()
            check = validate_dfm_file(dfm)
            if not check.ok:
                raise ValueError(check.message)
            root = resolve_deepfacelive_root(cfg.extra.get("deepfacelive_root"))
            if root is None:
                raise ValueError("未找到专用模型引擎；请选择解压后的 DeepFaceLive NVIDIA 安装目录")
            if detect_build_kind(root).kind != "nvidia":
                raise ValueError("此版本需要 NVIDIA 构建；不支持 DX12/DirectML 或无法识别的运行环境")
            python, main = _official_python(root), _official_main_py(root)
            if python is None or main is None:
                raise ValueError("引擎不完整：需要 _internal/python/python.exe 与 _internal/DeepFaceLive/main.py")
            source = main.parent
            for relative in ("modelhub/DFLive/DFMModel.py", "xlib/face/FLandmarks2D.py"):
                if not (source / relative).is_file():
                    raise ValueError(f"引擎缺少 {relative}；请完整解压 NVIDIA 安装包")
            if cfg.camera_index < 0 or not 160 <= cfg.width <= 1920 or not 120 <= cfg.height <= 1080:
                raise ValueError("摄像头编号或画面尺寸无效（支持 160×120 至 1920×1080）")
            provider, _, index = cfg.gpu_device.partition(":")
            if provider != "cuda" or int(index or 0) < 0:
                raise ValueError("专用模型模式需要 NVIDIA GPU，设备格式为 cuda:0")
            timeout = float(cfg.extra.get("facefusion_startup_timeout") or 120)
            if not math.isfinite(timeout) or not 10 <= timeout <= 600:
                raise ValueError("引擎启动等待时间必须为 10 至 600 秒")
            worker_config = {
                "root": str(root), "source_root": str(source), "dfm_path": str(dfm),
                "version": self.engine_version, "device_id": int(index or 0),
                "camera_index": cfg.camera_index, "width": cfg.width, "height": cfg.height,
                "fps": 30, "watermark": cfg.watermark_text,
            }
        except Exception as exc:
            with self._lock:
                self._error = str(exc)
            raise RuntimeError(str(exc)) from exc
        with self._lock:
            self._root, self._python, self._cfg = root, python, cfg
            self._worker_config, self._startup_timeout = worker_config, timeout
            self._status = EngineStatus.READY

    def _launch_env(self, python: Path) -> dict[str, str]:
        env = _worker_env(python)
        cuda = self._root / "_internal/CUDA"
        paths = [cuda / "bin", cuda, python.parent / "DLLs"]
        env["PATH"] = os.pathsep.join(str(p) for p in paths if p.is_dir()) + os.pathsep + env.get("PATH", "")
        env["CUDA_PATH"] = str(cuda)
        # Upstream caches devices in env vars; discover afresh in this interpreter.
        for key in list(env):
            if key.startswith("ORT_DEVICE"):
                env.pop(key)
        return env

    def set_source_faces(self, paths: list[str]) -> None:
        # A trained DFM already contains the source identity.
        return None


def create_engine(kind: str = "placeholder") -> FaceSwapEngine:
    kind = (kind or "placeholder").lower()
    if kind in ("deepfacelive", "dfl", "pro"):
        return DeepFaceLiveEngine()
    if kind in ("facefusion", "ff", "simple"):
        from face_swap_studio.engines.facefusion import create_facefusion_engine

        return create_facefusion_engine()
    from face_swap_studio.engines.placeholder import PlaceholderEngine

    return PlaceholderEngine()
