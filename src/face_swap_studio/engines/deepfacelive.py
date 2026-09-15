"""DeepFaceLive adapter — PRO mode (load .dfm).

DeepFaceLive is a separate Win app. Official CLI only accepts:
  python main.py run DeepFaceLive [--userdata-dir PATH] [--no-cuda]
.dfm models are staged into <userdata>/dfm_models/ and selected in the DFL UI
(Face swapper / DFM). This adapter stages the chosen .dfm and launches the app.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from face_swap_studio.engines.base import (
    EngineCapabilities,
    EngineConfig,
    EngineFrame,
    EngineStatus,
    FaceSwapEngine,
)

# Common Win install markers (relative to deepfacelive_root)
_LAUNCHERS = (
    "DeepFaceLive.bat",
    "DeepFaceLive.cmd",
    "main.py",
)


def resolve_deepfacelive_root(explicit: Optional[str] = None) -> Optional[Path]:
    """Find DeepFaceLive install directory."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("DEEPFACELIVE_ROOT") or os.environ.get("DFL_ROOT")
    if env:
        candidates.append(Path(env))
    # Common Windows locations (also checked on Linux for docs/tests)
    for base in (
        Path(r"C:\DeepFaceLive"),
        Path(r"C:\DeepFaceLive_NVIDIA"),
        Path.home() / "DeepFaceLive",
        Path.home() / "DeepFaceLive_NVIDIA",
    ):
        candidates.append(base)
    for root in candidates:
        if not root:
            continue
        root = root.expanduser()
        if any((root / name).exists() for name in _LAUNCHERS):
            return root.resolve()
    return None


def _userdata_dir(root: Path, override: Optional[str] = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    ud = root / "userdata"
    ud.mkdir(parents=True, exist_ok=True)
    return ud


def stage_dfm(dfm_path: Path, userdata: Path) -> Path:
    """Copy .dfm into userdata/dfm_models (DeepFaceLive discovers models there)."""
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
    """Build process argv for DeepFaceLive NVIDIA / DX12 builds."""
    bat = root / "DeepFaceLive.bat"
    cmd_file = root / "DeepFaceLive.cmd"
    main_py = root / "main.py"

    # Prefer bat on Windows; fall back to python main.py (same flags).
    if sys.platform == "win32" and bat.is_file():
        # bat wrappers often ignore extra args; still pass via env for docs.
        return [str(bat)]
    if sys.platform == "win32" and cmd_file.is_file():
        return [str(cmd_file)]

    py = sys.executable
    # Some packs ship python.exe beside main.py
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
        self._proc: Optional[subprocess.Popen] = None

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            name="deepfacelive",
            version="0.2.0",
            supports_live_camera=True,
            supports_gpu=True,
            notes=(
                "顶级模式：将 .dfm 放入 userdata/dfm_models 并启动 DeepFaceLive；"
                "在 DFL 界面 Face swapper 选该模型。优先 NVIDIA 构建；.dfm 须与导出它的 DFL 版本匹配。"
                "预览在 DeepFaceLive 窗口，壳侧 read_frame 不拉取帧。"
            ),
            is_stub=False,
        )

    def status(self) -> EngineStatus:
        if self._proc is not None and self._proc.poll() is not None:
            # Process exited
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
        if not path.is_file() or path.suffix.lower() != ".dfm":
            self._status = EngineStatus.ERROR
            self._error = f"无效的 .dfm：{path}"
            raise RuntimeError(self._error)
        self._dfm = path.resolve()

        root = resolve_deepfacelive_root(config.extra.get("deepfacelive_root"))
        if root is None:
            self._status = EngineStatus.ERROR
            self._error = (
                "未找到 DeepFaceLive 安装目录。请设置 extra.deepfacelive_root "
                "或环境变量 DEEPFACELIVE_ROOT（目录内需有 DeepFaceLive.bat 或 main.py）"
            )
            raise RuntimeError(self._error)
        self._root = root

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
        # Pro mode uses .dfm, not still-face paths; keep for shell compatibility.
        if self._cfg is not None:
            self._cfg.source_face_paths = list(paths)

    def read_frame(self) -> Optional[EngineFrame]:
        # External DFL UI owns the camera/preview; no frame bridge yet.
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
