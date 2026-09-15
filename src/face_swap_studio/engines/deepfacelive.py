"""DeepFaceLive adapter — PRO mode (load .dfm).

DeepFaceLive is a separate Win app. Official CLI only accepts:
  python main.py run DeepFaceLive [--userdata-dir PATH] [--no-cuda]
.dfm models are staged into <userdata>/dfm_models/ and selected in the DFL UI.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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

# Heuristic: real DFM (ONNX-based) packs are usually multi‑MB.
_MIN_DFM_BYTES = 512 * 1024


@dataclass(frozen=True)
class BuildInfo:
    kind: str  # "nvidia" | "dx12" | "unknown"
    evidence: str


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
        if any((root / name).exists() for name in _LAUNCHERS):
            return root.resolve()
    return None


def detect_build_kind(root: Path) -> BuildInfo:
    """Classify NVIDIA vs DX12 build from path + shipped binaries."""
    name = root.name.lower()
    text_blob = name
    # Collect a few file names one level deep (cheap).
    try:
        names = [p.name.lower() for p in root.iterdir() if p.is_file()]
    except OSError:
        names = []
    text_blob += " " + " ".join(names[:80])

    nvidia_hits = []
    if "nvidia" in name or "cuda" in name:
        nvidia_hits.append(f"路径含 NVIDIA/CUDA：{root.name}")
    cuda_dlls = [
        n
        for n in names
        if n.startswith("cudnn")
        or n.startswith("cublas")
        or n.startswith("cudart")
        or "nvinfer" in n
    ]
    if cuda_dlls:
        nvidia_hits.append(f"发现 CUDA 相关文件：{', '.join(cuda_dlls[:4])}")

    dx_hits = []
    if "dx12" in name or "directx" in name:
        dx_hits.append(f"路径含 DX12/DirectX：{root.name}")
    dx_dlls = [n for n in names if "d3d12" in n or n.endswith("_dx12.dll")]
    if dx_dlls:
        dx_hits.append(f"发现 DX12 相关文件：{', '.join(dx_dlls[:4])}")

    if nvidia_hits and not dx_hits:
        return BuildInfo("nvidia", "; ".join(nvidia_hits))
    if dx_hits and not nvidia_hits:
        return BuildInfo("dx12", "; ".join(dx_hits))
    if nvidia_hits and dx_hits:
        # Mixed → prefer nvidia if cuda dlls present
        if cuda_dlls:
            return BuildInfo("nvidia", "; ".join(nvidia_hits + dx_hits))
        return BuildInfo("dx12", "; ".join(dx_hits + nvidia_hits))
    return BuildInfo("unknown", "未在安装目录检测到明确的 NVIDIA/CUDA 或 DX12 标记")


def validate_dfm_file(
    path: Path,
    *,
    expected_hint: Optional[str] = None,
) -> DfmCheck:
    """Preflight .dfm before staging. Readable Chinese errors on failure.

    DeepFaceLive treats .dfm as ONNX-compatible graphs. We cannot fully load
    without onnxruntime; we do size + ONNX/protobuf fingerprint checks, and
    optional sidecar / filename version hint matching.
    """
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
    # ONNX ModelProto often embeds the ASCII token "onnx" / "ONNX"
    looks_onnx = (b"onnx" in head.lower()) or head.startswith(b"\x08")
    if not looks_onnx:
        return DfmCheck(
            False,
            f".dfm 未通过格式预检（未见 ONNX/模型指纹）：{path.name}。"
            "常见原因：①文件损坏或下到一半；②不是 DeepFaceLive 用的专模；"
            "③用错版本的 DeepFaceLab 导出。请用与本机 DeepFaceLive 同代的 DFL 重新导出 .dfm。",
            size,
        )

    # Optional explicit version hint from config or sidecar
    sidecar = path.with_suffix(path.suffix + ".version")
    if not sidecar.is_file():
        sidecar = path.with_suffix(".version")
    hint = (expected_hint or "").strip()
    if not hint and sidecar.is_file():
        hint = sidecar.read_text(encoding="utf-8", errors="ignore").strip()

    # Filename pattern e.g. face_SAEH64 or _224 / _320 — informational only unless expected set
    if hint:
        # Accept if hint appears in filename or sidecar already matched content
        stem = path.stem.lower()
        if hint.lower() not in stem and hint.lower() not in path.name.lower():
            # Still allow if sidecar equals hint (already loaded from sidecar)
            if not (sidecar.is_file() and sidecar.read_text(encoding="utf-8", errors="ignore").strip() == hint):
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


def build_launch_command(
    root: Path,
    userdata: Path,
    *,
    no_cuda: bool = False,
) -> list[str]:
    bat = root / "DeepFaceLive.bat"
    cmd_file = root / "DeepFaceLive.cmd"
    main_py = root / "main.py"

    if sys.platform == "win32" and bat.is_file():
        return [str(bat)]
    if sys.platform == "win32" and cmd_file.is_file():
        return [str(cmd_file)]

    py = sys.executable
    bundled = root / "python.exe"
    if bundled.is_file():
        py = str(bundled)

    if not main_py.is_file():
        raise FileNotFoundError(f"未找到 DeepFaceLive 入口: {root}")

    cmd = [py, str(main_py), "run", "DeepFaceLive", "--userdata-dir", str(userdata)]
    if no_cuda:
        cmd.append("--no-cuda")
    return cmd


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
        self._proc: Optional[subprocess.Popen] = None

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            name="deepfacelive",
            version="0.3.0",
            supports_live_camera=True,
            supports_gpu=True,
            notes=(
                "顶级模式：校验 NVIDIA 构建 + .dfm 预检后，将模型放入 userdata/dfm_models 并启动 DeepFaceLive；"
                "在 DFL 界面 Face swapper 选该模型。预览在 DeepFaceLive 窗口。"
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
                "（目录内需有 DeepFaceLive.bat 或 main.py）。"
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
                "检测到 DeepFaceLive **DX12 构建**，顶级实时请改用 **NVIDIA 构建**（RTX 更快）。"
                f"依据：{build.evidence}。安装目录：{root}"
            )
            raise RuntimeError(self._error)
        if require_nvidia and build.kind == "unknown":
            # Soft-fail only if allow_unknown_build is set; default warn via error for P0 clarity
            allow_unknown = bool(config.extra.get("allow_unknown_build"))
            if not allow_unknown:
                self._status = EngineStatus.ERROR
                self._error = (
                    "无法确认是否为 NVIDIA 构建。"
                    f"{build.evidence}。请指向含 CUDA/cudnn 的 NVIDIA 包目录，"
                    f"或在 extra 中设 allow_unknown_build=true（不推荐）。目录：{root}"
                )
                raise RuntimeError(self._error)

        ud_override = config.extra.get("userdata_dir")
        self._userdata = _userdata_dir(root, ud_override)
        self._staged = stage_dfm(self._dfm, self._userdata)

        self._status = EngineStatus.READY
        self._error = None

    def start(self) -> None:
        if self._status not in (EngineStatus.READY, EngineStatus.RUNNING):
            raise RuntimeError(self._error or "引擎未就绪")
        if self._proc is not None and self._proc.poll() is None:
            self._status = EngineStatus.RUNNING
            return
        assert self._root is not None and self._userdata is not None

        no_cuda = bool(self._cfg and self._cfg.extra.get("no_cuda"))
        cmd = build_launch_command(self._root, self._userdata, no_cuda=no_cuda)
        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(self._root),
                env={**os.environ},
            )
        except OSError as exc:
            self._status = EngineStatus.ERROR
            self._error = f"无法启动 DeepFaceLive：{exc}"
            raise RuntimeError(self._error) from exc

        self._status = EngineStatus.RUNNING

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        if self._status == EngineStatus.RUNNING:
            self._status = EngineStatus.READY

    def set_source_faces(self, paths: list[str]) -> None:
        if self._cfg is not None:
            self._cfg.source_face_paths = list(paths)

    def read_frame(self) -> Optional[EngineFrame]:
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
    if kind in ("facefusion", "ff", "simple"):
        from face_swap_studio.engines.facefusion_stub import create_facefusion_engine

        return create_facefusion_engine()
    from face_swap_studio.engines.placeholder import PlaceholderEngine

    return PlaceholderEngine()
