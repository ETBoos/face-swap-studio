"""即用 mode launches Deep-Live-Cam; it does not implement a swap."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from face_swap_studio.engines.base import EngineConfig, EngineStatus
from face_swap_studio.engines.deeplivecam import (
    DeepLiveCamEngine,
    build_live_command,
    build_preview_command,
    resolve_deeplivecam_python,
    resolve_deeplivecam_root,
)
from face_swap_studio.engines.dlc_live_bootstrap import (
    apply_source_pin,
    build_child_argv,
    install_core_source_pin,
)


def _png(path: Path, color: tuple[int, int, int] = (0, 0, 255)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = np.zeros((24, 32, 3), dtype=np.uint8)
    img[:] = color
    assert cv2.imwrite(str(path), img)
    return path


def _dlc_root(root: Path) -> Path:
    (root / "modules").mkdir(parents=True)
    (root / "run.py").write_text("print('dlc')\n", encoding="utf-8")
    (root / "modules" / "core.py").write_text("# core\n", encoding="utf-8")
    py = root / "venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    py.chmod(0o755)
    return root


def _clear_dlc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEP_LIVE_CAM_ROOT", raising=False)
    monkeypatch.delenv("DLC_ROOT", raising=False)
    monkeypatch.delenv("DEEP_LIVE_CAM_PYTHON", raising=False)
    monkeypatch.delenv("DLC_PYTHON", raising=False)


def test_resolve_root_env_and_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_dlc_env(monkeypatch)
    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    assert resolve_deeplivecam_root(str(root)) == root.resolve()
    monkeypatch.setenv("DEEP_LIVE_CAM_ROOT", str(root))
    assert resolve_deeplivecam_root(None) == root.resolve()
    assert resolve_deeplivecam_root(str(tmp_path / "missing")) is None
    assert resolve_deeplivecam_python(root, None) == (root / "venv" / "bin" / "python").resolve()


def test_explicit_root_does_not_fall_back_to_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    monkeypatch.setenv("DLC_ROOT", str(root))
    eng = DeepLiveCamEngine()
    face = _png(tmp_path / "face.png")
    with pytest.raises(RuntimeError, match="deeplivecam_root"):
        eng.initialize(
            EngineConfig(
                source_face_paths=[str(face)],
                extra={"deeplivecam_root": str(tmp_path / "not-dlc"), "dlc_session": "preview"},
            )
        )


def test_preview_command_is_upstream_headless_cli(tmp_path: Path) -> None:
    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    py = root / "venv" / "bin" / "python"
    source = tmp_path / "a.png"
    target = tmp_path / "b.png"
    output = tmp_path / "out.png"
    cmd = build_preview_command(
        py,
        root,
        source,
        target,
        output,
        provider="cuda",
        frame_processors=["face_swapper"],
    )
    assert cmd[0] == str(py)
    assert cmd[1] == str(root / "run.py")
    assert cmd[cmd.index("-s") + 1] == str(source)
    assert cmd[cmd.index("-t") + 1] == str(target)
    assert cmd[cmd.index("-o") + 1] == str(output)
    assert cmd[cmd.index("--frame-processor") + 1] == "face_swapper"
    assert cmd[cmd.index("--execution-provider") + 1] == "cuda"
    assert "dlc_live_bootstrap.py" not in " ".join(cmd)


def test_live_child_argv_omits_source_so_gui_stays(tmp_path: Path) -> None:
    run_py = tmp_path / "run.py"
    child = build_child_argv(run_py, provider="cuda", live_mirror=True, lang="en")
    assert child[0] == str(run_py)
    for flag in ("-s", "--source", "-t", "--target", "-o", "--output"):
        assert flag not in child
    assert "--live-mirror" in child
    assert child[child.index("--execution-provider") + 1] == "cuda"

    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    cmd = build_live_command(
        root / "venv" / "bin" / "python",
        root,
        tmp_path / "face.png",
        provider="cuda",
    )
    assert cmd[1].endswith("dlc_live_bootstrap.py")
    assert "-s" not in cmd
    assert "--source" in cmd  # bootstrap flag, not run.py -s
    assert "run.py" not in cmd


def test_preview_initialize_and_first_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_dlc_env(monkeypatch)
    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    face = _png(tmp_path / "face.png", (10, 20, 30))
    target = _png(tmp_path / "target.png", (1, 2, 3))
    eng = DeepLiveCamEngine()
    eng.initialize(
        EngineConfig(
            gpu_device="cuda:0",
            source_face_paths=[str(face)],
            watermark_text=None,
            extra={
                "deeplivecam_root": str(root),
                "dlc_session": "preview",
                "preview_target": str(target),
            },
        )
    )
    assert eng.status() == EngineStatus.READY
    assert eng._preview_cmd is not None
    assert "--execution-provider" in eng._preview_cmd
    assert eng._preview_cmd[eng._preview_cmd.index("--execution-provider") + 1] == "cuda"

    def fake_popen(cmd, **kwargs):
        out = cmd[cmd.index("-o") + 1]
        swapped = np.full((24, 32, 3), 9, dtype=np.uint8)
        assert cv2.imwrite(out, swapped)
        proc = MagicMock()
        proc.poll.return_value = 0
        return proc

    with patch(
        "face_swap_studio.engines.deeplivecam.subprocess.Popen",
        side_effect=fake_popen,
    ) as popen:
        eng.start()
        popen.assert_called_once()
        launched = popen.call_args.args[0]
        assert launched[1].endswith("run.py")
        frame = eng.read_frame()
    assert frame is not None
    assert frame.image.shape == (24, 32, 3)
    assert frame.meta["kind"] == "first_frame"
    assert frame.meta["live_camera_loop"] is False
    assert frame.meta["hardware_verified"] is False
    assert frame.meta["engine"] == "deeplivecam"
    assert int(frame.image[0, 0, 0]) == 9


def test_live_start_does_not_invent_a_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_dlc_env(monkeypatch)
    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    face = _png(tmp_path / "face.png")
    eng = DeepLiveCamEngine()
    eng.initialize(
        EngineConfig(
            source_face_paths=[str(face)],
            extra={"deeplivecam_root": str(root), "dlc_session": "live"},
        )
    )
    proc = MagicMock()
    proc.poll.return_value = None
    with patch("face_swap_studio.engines.deeplivecam.subprocess.Popen", return_value=proc) as popen:
        eng.start()
        cmd = popen.call_args.args[0]
    assert eng.status() == EngineStatus.RUNNING
    assert eng.read_frame() is None
    assert cmd[1].endswith("dlc_live_bootstrap.py")
    assert "-s" not in cmd
    eng.stop()
    proc.terminate.assert_called()


def test_missing_source_and_bad_provider(tmp_path: Path) -> None:
    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    eng = DeepLiveCamEngine()
    with pytest.raises(RuntimeError, match="源脸"):
        eng.initialize(
            EngineConfig(
                extra={
                    "deeplivecam_root": str(root),
                    "preview_target": str(tmp_path / "t.png"),
                }
            )
        )
    face = _png(tmp_path / "face.png")
    target = _png(tmp_path / "target.png")
    with pytest.raises(RuntimeError, match="execution_provider"):
        eng.initialize(
            EngineConfig(
                source_face_paths=[str(face)],
                extra={
                    "deeplivecam_root": str(root),
                    "preview_target": str(target),
                    "execution_provider": "not-a-provider",
                },
            )
        )


def test_import_hook_pins_source_and_keeps_gui(tmp_path: Path) -> None:
    pkg = tmp_path / "fakeroot"
    (pkg / "modules").mkdir(parents=True)
    (pkg / "modules" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "modules" / "globals.py").write_text(
        "source_path=None\nheadless=True\n", encoding="utf-8"
    )
    (pkg / "modules" / "core.py").write_text(
        "def parse_args():\n"
        "    import modules.globals as g\n"
        "    g.headless = True\n"
        "    g.source_path = None\n",
        encoding="utf-8",
    )
    poisoned = [name for name in sys.modules if name == "modules" or name.startswith("modules.")]
    for name in poisoned:
        del sys.modules[name]
    sys.path.insert(0, str(pkg))
    finder = install_core_source_pin(r"C:\faces\actor.jpg")
    try:
        import modules.core as core
        import modules.globals as globals_mod

        core.parse_args()
        assert globals_mod.source_path == r"C:\faces\actor.jpg"
        assert globals_mod.headless is False
        apply_source_pin(globals_mod, r"D:\other.png")
        assert globals_mod.source_path == r"D:\other.png"
        assert globals_mod.headless is False
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        sys.path.remove(str(pkg))
        for name in list(sys.modules):
            if name == "modules" or name.startswith("modules."):
                del sys.modules[name]
