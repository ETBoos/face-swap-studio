"""Persisted shell settings. Standard library only.

Windows setup (``scripts/setup-all-win.bat``) writes
``%USERPROFILE%\\FaceSwapStudio\\settings.json`` with the same module, before
the GUI starts, so the user never types a Deep-Live-Cam path.

Pro / DeepFaceLive keys in that file are left alone.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SETTINGS_FILE_NAME = "settings.json"

# Shown instead of the engine's "未找到 Deep-Live-Cam" dialog when the
# directory is still empty and the one-click installer can run.
DLC_SETUP_OFFER_ZH = (
    "还没有找到换脸组件 Deep-Live-Cam，所以还不能开始。\n\n"
    "点「一键安装」会把它装到你的用户文件夹，并自动写好路径。\n"
    "不用自己填目录。装完后双击桌面上的「打开换脸」。"
)

DLC_SETUP_OFFER_NO_SCRIPT_ZH = (
    "还没有找到换脸组件 Deep-Live-Cam，所以还不能开始。\n\n"
    "请双击 scripts\\setup-all-win.bat 。"
    "它会安装组件、自动写好路径，并在桌面创建「打开换脸」。"
)


def default_settings() -> dict[str, Any]:
    """In-memory defaults. Empty deeplivecam_root means "probe on startup"."""
    return {
        "width": 1280,
        "height": 720,
        "camera_index": 0,
        "gpu_device": "cuda:0",
        "engine": "placeholder",
        "work_mode": "simple",
        "dfm_path": "",
        "facefusion_root": "",
        "deepfacelive_root": "",
        "userdata_dir": "",
        "deeplivecam_root": "",
        "deeplivecam_python": "",
        "dlc_session": "preview",
        "execution_provider": "",
        "preview_target": "",
        "instant_source_face": "",
    }


def default_settings_path() -> Path:
    """Production file next to license.json under the user profile."""
    return Path.home() / "FaceSwapStudio" / SETTINGS_FILE_NAME


def resolve_settings_path(projects_root: Path) -> Path:
    """Settings sit beside license.json (parent of the projects folder).

    ``FSS_SETTINGS_PATH`` overrides that for tests and custom layouts.
    """
    override = os.environ.get("FSS_SETTINGS_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return projects_root.parent / SETTINGS_FILE_NAME


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return raw


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """Defaults overlaid with the JSON file. Unknown keys are kept."""
    merged = default_settings()
    merged.update(_read_json_dict(path or default_settings_path()))
    return merged


def save_settings(settings: Mapping[str, Any], path: Path | None = None) -> Path:
    """Merge ``settings`` into the existing file so omitted keys survive."""
    file = path or default_settings_path()
    file.parent.mkdir(parents=True, exist_ok=True)
    current = _read_json_dict(file)
    current.update(dict(settings))
    file.write_text(
        json.dumps(current, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return file


def looks_like_deeplivecam_root(root: Path) -> bool:
    return (root / "run.py").is_file() and (root / "modules" / "core.py").is_file()


def deeplivecam_candidates() -> list[Path]:
    """Env first, then the usual Windows install locations.

    ``%USERPROFILE%\\Deep-Live-Cam`` is ``Path.home() / "Deep-Live-Cam"``.
    """
    candidates: list[Path] = []
    for key in ("DEEP_LIVE_CAM_ROOT", "DLC_ROOT"):
        env = os.environ.get(key)
        if env and env.strip():
            candidates.append(Path(env.strip()).expanduser())
    candidates.extend(
        (
            Path(r"C:\Deep-Live-Cam"),
            Path(r"D:\Deep-Live-Cam"),
            Path.home() / "Deep-Live-Cam",
            Path(r"C:\DeepLiveCam"),
            Path.home() / "DeepLiveCam",
        )
    )
    return candidates


def probe_deeplivecam_root() -> Path | None:
    """First candidate that looks like a Deep-Live-Cam checkout."""
    seen: set[Path] = set()
    for root in deeplivecam_candidates():
        try:
            key = root.expanduser()
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        if looks_like_deeplivecam_root(key):
            return key.resolve()
    return None


def ensure_deeplivecam_root(settings: dict[str, Any]) -> str | None:
    """Fill ``deeplivecam_root`` when it is empty and a checkout exists.

    A non-empty value is left unchanged even if it is not a real install.
    That matches the engine: an explicit path must not fall through to
    another copy. Returns the path string when settings now point at a
    real checkout.
    """
    current = str(settings.get("deeplivecam_root") or "").strip()
    if current:
        root = Path(current).expanduser()
        try:
            valid = looks_like_deeplivecam_root(root)
        except OSError:
            valid = False
        if not valid:
            return None
        resolved = str(root.resolve())
        settings["deeplivecam_root"] = resolved
        return resolved
    found = probe_deeplivecam_root()
    if found is None:
        return None
    settings["deeplivecam_root"] = str(found)
    return str(found)


def write_deeplivecam_root(root: str, path: Path | None = None) -> Path:
    """Record the install directory. Does not switch Pro over to Instant."""
    file = path or default_settings_path()
    settings = load_settings(file)
    resolved = str(Path(root).expanduser().resolve())
    settings["deeplivecam_root"] = resolved
    return save_settings(settings, file)


def find_cpu_setup_script() -> Path | None:
    """``setup-deeplivecam-cpu-win.bat`` beside the one-click installer."""
    setup_all = find_setup_all_script()
    if setup_all is None:
        return None
    cpu = setup_all.with_name("setup-deeplivecam-cpu-win.bat")
    return cpu.resolve() if cpu.is_file() else None


def find_setup_all_script() -> Path | None:
    """Locate ``scripts/setup-all-win.bat`` from a source checkout or cwd."""
    candidates: list[Path] = []
    env = os.environ.get("FSS_SETUP_SCRIPT", "").strip()
    if env:
        candidates.append(Path(env).expanduser())
    here = Path(__file__).resolve()
    # core/studio_settings.py → face_swap_studio → src → repo root
    if len(here.parents) >= 4:
        candidates.append(here.parents[3] / "scripts" / "setup-all-win.bat")
    candidates.append(Path.cwd() / "scripts" / "setup-all-win.bat")
    seen: set[Path] = set()
    for cand in candidates:
        try:
            key = cand.resolve() if cand.exists() else cand
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        if cand.is_file():
            return cand.resolve()
    return None


def launch_setup_script(script: Path) -> None:
    """Open the Windows one-click installer. No-op is not attempted elsewhere."""
    if not script.is_file():
        raise OSError(f"找不到安装脚本：{script}")
    if os.name != "nt":
        raise OSError("一键安装脚本只能在 Windows 上运行")
    os.startfile(str(script))  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write deeplivecam_root into FaceSwap Studio settings.json"
    )
    parser.add_argument("--deeplivecam-root", required=True)
    parser.add_argument(
        "--settings",
        default="",
        help="settings.json path (default: %%USERPROFILE%%\\FaceSwapStudio\\settings.json)",
    )
    args = parser.parse_args(argv)
    root = Path(args.deeplivecam_root).expanduser()
    if not looks_like_deeplivecam_root(root):
        print(
            "[错误] 不是 Deep-Live-Cam 目录（需要 run.py 以及 modules\\core.py）："
            f"{root}",
            file=sys.stderr,
        )
        return 1
    dest = Path(args.settings).expanduser() if str(args.settings).strip() else None
    written = write_deeplivecam_root(str(root), dest)
    print(f"[OK] 已写入 {written}")
    print(f"     deeplivecam_root={root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
