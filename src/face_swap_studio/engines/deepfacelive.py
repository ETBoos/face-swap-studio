"""DeepFaceLive adapter — PRO mode (load .dfm).

Official portable NVIDIA layout (iperov WindowsBuilder):
  <root>/DeepFaceLive.bat
  <root>/userdata/dfm_models/
  <root>/_internal/CUDA/bin/*.dll
  <root>/_internal/python/python.exe
  <root>/_internal/DeepFaceLive/main.py

Official DeepFaceLive.bat hardcodes --userdata-dir="%~dp0userdata".
When userdata_dir is customized we must launch via python + --userdata-dir.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from face_swap_studio.engines.base import (
    EngineCapabilities,
    EngineConfig,
    EngineFrame,
    EngineStatus,
    FaceSwapEngine,
)

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


def resolve_deepfacelive_root(explicit: Optional[str] = None) -> Optional[Path]:
    """Find DeepFaceLive install directory (NVIDIA paths preferred in order)."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("DEEPFACELIVE_ROOT") or os.environ.get("DFL_ROOT")
    if env:
        candidates.append(Path(env))
    for base in (
        Path(r"C:\DeepFaceLive_NVIDIA"),
        Path.home() / "DeepFaceLive_NVIDIA",
        Path(r"C:\DeepFaceLive"),
        Path.home() / "DeepFaceLive",
    ):
        candidates.append(base)
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
    if (root / "_internal" / "python" / "python.exe").is_file() and (
        root / "DeepFaceLive.bat"
    ).is_file():
        return True
    return False


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
    expected_hint: Optional[str] = None,
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

    head = path.read_bytes()[:4096]
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
        if hint.lower() not in stem and hint.lower() not in path.name.lower():
            if not (
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


def _userdata_dir(root: Path, override: Optional[str] = None) -> Path:
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


def _official_python(root: Path) -> Optional[Path]:
    for cand in (
        root / "_internal" / "python" / "python.exe",
        root / "_internal" / "python" / "python",
        root / "python.exe",
    ):
        if cand.is_file():
            return cand
    return None


def _official_main_py(root: Path) -> Optional[Path]:
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


class DeepFaceLiveEngine(FaceSwapEngine):
    """Launch DeepFaceLive with a staged .dfm; preview stays in DFL's own window."""

    def __init__(self) -> None:
        self._cfg: Optional[EngineConfig] = None
        self._status = EngineStatus.STUB
        self._error: Optional[str] = None
        self._dfm: Optional[Path] = None
        self._staged: Optional[Path] = None
        self._root: Optional[Path] = None
        self._userdata: Optional[Path] = None
        self._build: Optional[BuildInfo] = None
        self._launch_cmd: Optional[list[str]] = None
        self._proc: Optional[subprocess.Popen] = None

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            name="deepfacelive",
            version="0.4.0",
            supports_live_camera=True,
            supports_gpu=True,
            notes=(
                "顶级模式：识别官方 _internal/CUDA 便携包；自定义 userdata 走 python "
                "--userdata-dir；.dfm 预检后写入 userdata/dfm_models。"
                "RUNNING≠已加载模型≠首帧；需在 DFL UI 选 Face swapper。"
            ),
            is_stub=False,
        )

    def status(self) -> EngineStatus:
        if self._proc is not None and self._proc.poll() is not None:
            code = self._proc.returncode
            self._proc = None
            if self._status == EngineStatus.RUNNING:
                if code and code != 0:
                    self._status = EngineStatus.ERROR
                    self._error = f"DeepFaceLive 进程退出 code={code}"
                else:
                    self._status = EngineStatus.READY
        return self._status

    def initialize(self, config: EngineConfig) -> None:
        self._cfg = config
        self._error = None
        self._launch_cmd = None

        dfm_raw = (config.extra.get("dfm_path") or "").strip()
        if not dfm_raw:
            self._status = EngineStatus.ERROR
            self._error = "顶级模式需要有效的 .dfm 文件路径（extra.dfm_path）"
            raise RuntimeError(self._error)

        path = Path(dfm_raw).expanduser()
        check = validate_dfm_file(
            path,
            expected_hint=(config.extra.get("dfm_version_hint") or None),
        )
        if not check.ok:
            self._status = EngineStatus.ERROR
            self._error = check.message
            raise RuntimeError(self._error)
        self._dfm = path.resolve()

        root = resolve_deepfacelive_root(config.extra.get("deepfacelive_root"))
        if root is None:
            self._status = EngineStatus.ERROR
            self._error = (
                "未找到 DeepFaceLive 安装目录。请安装 **NVIDIA 构建**，并设置 "
                "extra.deepfacelive_root 或环境变量 DEEPFACELIVE_ROOT"
                "（目录内需有 DeepFaceLive.bat 或 _internal/DeepFaceLive/main.py）。"
            )
            raise RuntimeError(self._error)
        self._root = root

        build = detect_build_kind(root)
        self._build = build
        require_nvidia = config.extra.get("require_nvidia")
        if require_nvidia is None:
            require_nvidia = True
        if require_nvidia and build.kind == "dx12":
            self._status = EngineStatus.ERROR
            self._error = (
                "检测到 DeepFaceLive **DX12/DirectML 构建**，顶级实时请改用 **NVIDIA 构建**。"
                f"依据：{build.evidence}。provider={build.provider}。安装目录：{root}"
            )
            raise RuntimeError(self._error)
        if require_nvidia and build.kind == "unknown":
            allow_unknown = bool(config.extra.get("allow_unknown_build"))
            if not allow_unknown:
                self._status = EngineStatus.ERROR
                self._error = (
                    "无法确认是否为 NVIDIA 构建。"
                    f"{build.evidence}。请指向含 _internal/CUDA/bin 的官方 NVIDIA 便携包，"
                    f"或设 allow_unknown_build=true（不推荐）。目录：{root}"
                )
                raise RuntimeError(self._error)

        ud_override = config.extra.get("userdata_dir")
        self._userdata = _userdata_dir(root, ud_override)
        self._staged = stage_dfm(self._dfm, self._userdata)

        no_cuda = bool(config.extra.get("no_cuda"))
        self._launch_cmd = build_launch_command(
            root, self._userdata, no_cuda=no_cuda
        )

        self._status = EngineStatus.READY
        self._error = None

    def start(self) -> None:
        if self._status not in (EngineStatus.READY, EngineStatus.RUNNING):
            raise RuntimeError(self._error or "引擎未就绪")
        if self._proc is not None and self._proc.poll() is None:
            self._status = EngineStatus.RUNNING
            return
        assert self._root is not None and self._userdata is not None
        cmd = self._launch_cmd or build_launch_command(self._root, self._userdata)
        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(self._root),
                env=launch_env(self._root),
            )
        except OSError as exc:
            self._status = EngineStatus.ERROR
            self._error = f"无法启动 DeepFaceLive：{exc}；cmd={cmd}"
            raise RuntimeError(self._error) from exc

        self._status = EngineStatus.RUNNING

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                try:
                    self._proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
        self._proc = None
        if self._status == EngineStatus.RUNNING:
            self._status = EngineStatus.READY

    def set_source_faces(self, paths: list[str]) -> None:
        if self._cfg is not None:
            self._cfg.source_face_paths = list(paths)

    def read_frame(self) -> Optional[EngineFrame]:
        # External DFL UI owns preview; RUNNING ≠ 首帧出画.
        return None

    def last_error(self) -> Optional[str]:
        return self._error

    def shutdown(self) -> None:
        try:
            self.stop()
        except Exception:
            pass


def create_engine(kind: str = "placeholder") -> FaceSwapEngine:
    kind = (kind or "placeholder").lower()
    if kind in ("deepfacelive", "dfl", "pro"):
        return DeepFaceLiveEngine()
    # 即用. "facefusion" remains a legacy alias so old settings do not
    # resurrect the FaceFusion stub.
    if kind in ("deeplivecam", "dlc", "simple", "facefusion", "ff"):
        from face_swap_studio.engines.deeplivecam import DeepLiveCamEngine

        return DeepLiveCamEngine()
    from face_swap_studio.engines.placeholder import PlaceholderEngine

    return PlaceholderEngine()
