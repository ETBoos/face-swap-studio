"""Instant-mode environment check. Standard library plus a short subprocess.

The Studio window calls this from 「环境监测」. A complete Deep-Live-Cam
checkout (directory, venv, insightface, runtime deps, inswapper model) is
recorded into settings and nothing is downloaded. Anything missing is left
for the existing Windows CPU setup script.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from face_swap_studio.core.studio_settings import (
    looks_like_deeplivecam_root,
    probe_deeplivecam_root,
)
from face_swap_studio.engines.deeplivecam import (
    inswapper_present,
    resolve_deeplivecam_python,
)

# Prebuilt insightface wheels in scripts/setup-deeplivecam-cpu-win.bat.
_WHEEL_MINORS = {11, 12, 13}
_DEP_MODULES = ("cv2", "onnxruntime")

Runner = Callable[[list[str]], "CommandResult"]


@dataclass
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class EnvCheckItem:
    key: str
    label: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class EnvReport:
    items: tuple[EnvCheckItem, ...]
    deeplivecam_root: str = ""
    deeplivecam_python: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.items) and all(item.ok for item in self.items)

    def summary_zh(self) -> str:
        lines = []
        for item in self.items:
            mark = "已有" if item.ok else "缺少"
            lines.append(f"{mark}  {item.label}：{item.detail}")
        return "\n".join(lines)


def default_runner(argv: list[str]) -> CommandResult:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(returncode=1, stderr=str(exc))
    return CommandResult(
        returncode=int(proc.returncode),
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )


def _import_ok(python: Path, module: str, runner: Runner) -> tuple[bool, str]:
    proc = runner([str(python), "-c", f"import {module}"])
    if proc.returncode == 0:
        return True, "可导入"
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    detail = tail[-1] if tail else f"退出码 {proc.returncode}"
    return False, detail


def _venv_version(python: Path, runner: Runner) -> tuple[int, int] | None:
    proc = runner(
        [
            str(python),
            "-c",
            "import sys; print(sys.version_info[0], sys.version_info[1])",
        ]
    )
    if proc.returncode != 0:
        return None
    parts = (proc.stdout or "").split()
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _locate_root(settings: dict[str, Any]) -> Path | None:
    current = str(settings.get("deeplivecam_root") or "").strip()
    if current:
        root = Path(current).expanduser()
        try:
            if looks_like_deeplivecam_root(root):
                return root.resolve()
        except OSError:
            return None
        # An explicit path that is not DLC must not fall through.
        return None
    return probe_deeplivecam_root()


def assess_instant_environment(
    settings: dict[str, Any] | None = None,
    *,
    runner: Runner | None = None,
) -> EnvReport:
    """Detect Python, Deep-Live-Cam, insightface, deps, and the swap model."""
    settings = settings or {}
    run = runner or default_runner
    items: list[EnvCheckItem] = []

    major, minor = sys.version_info[:2]
    studio_ok = (major, minor) >= (3, 11) and minor in _WHEEL_MINORS
    if studio_ok:
        py_detail = f"{major}.{minor}（可安装 cp{minor} 预编译包）"
    elif (major, minor) >= (3, 11):
        py_detail = f"{major}.{minor} 没有对应的预编译 insightface 轮（仅 3.11 / 3.12 / 3.13）"
    else:
        py_detail = f"{major}.{minor}，需要 3.11、3.12 或 3.13"
    items.append(EnvCheckItem("python", "Python", studio_ok, py_detail))

    root = _locate_root(settings)
    if root is None:
        items.append(EnvCheckItem("dlc", "Deep-Live-Cam", False, "未找到安装目录"))
        items.append(EnvCheckItem("dlc_python", "DLC 虚拟环境", False, "没有目录，跳过"))
        items.append(EnvCheckItem("insightface", "insightface", False, "没有 DLC Python，跳过"))
        items.append(EnvCheckItem("deps", "依赖", False, "没有 DLC Python，跳过"))
        items.append(EnvCheckItem("model", "换脸模型", False, "没有目录，跳过"))
        return EnvReport(items=tuple(items))

    items.append(EnvCheckItem("dlc", "Deep-Live-Cam", True, str(root)))
    explicit_py = str(settings.get("deeplivecam_python") or "").strip() or None
    python = resolve_deeplivecam_python(root, explicit_py)
    if python is None:
        items.append(
            EnvCheckItem("dlc_python", "DLC 虚拟环境", False, "未找到 venv\\Scripts\\python.exe")
        )
        items.append(EnvCheckItem("insightface", "insightface", False, "没有 DLC Python，跳过"))
        items.append(EnvCheckItem("deps", "依赖", False, "没有 DLC Python，跳过"))
    else:
        version = _venv_version(python, run)
        if version is None:
            py_ok = False
            py_text = f"{python}（无法读取版本）"
        else:
            py_ok = version[0] == 3 and version[1] in _WHEEL_MINORS
            py_text = f"{python}（{version[0]}.{version[1]}）"
            if not py_ok:
                py_text += "，预编译轮仅支持 3.11 / 3.12 / 3.13"
        items.append(EnvCheckItem("dlc_python", "DLC 虚拟环境", py_ok, py_text))
        face_ok, face_detail = _import_ok(python, "insightface", run)
        items.append(EnvCheckItem("insightface", "insightface", face_ok, face_detail))
        dep_bits = []
        deps_ok = True
        for module in _DEP_MODULES:
            ok, detail = _import_ok(python, module, run)
            deps_ok = deps_ok and ok
            dep_bits.append(f"{module} {'OK' if ok else detail}")
        items.append(EnvCheckItem("deps", "依赖", deps_ok, "；".join(dep_bits)))

    model_ok = inswapper_present(root)
    model_detail = "inswapper 已在 models\\" if model_ok else "缺少 inswapper_128 或 fp16 模型"
    items.append(EnvCheckItem("model", "换脸模型", model_ok, model_detail))
    return EnvReport(
        items=tuple(items),
        deeplivecam_root=str(root),
        deeplivecam_python=str(python) if python is not None else "",
    )


def apply_ready_environment(settings: dict[str, Any], report: EnvReport) -> bool:
    """Write detected paths. Does not change Pro mode or license fields.

    Returns True when a path was stored. No-op if the report is not ready.
    """
    if not report.ready or not report.deeplivecam_root:
        return False
    settings["deeplivecam_root"] = report.deeplivecam_root
    if report.deeplivecam_python:
        settings["deeplivecam_python"] = report.deeplivecam_python
    return True
