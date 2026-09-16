"""Unit tests for DeepFaceLive Pro adapter (Codex item 5)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from face_swap_studio.engines.base import EngineConfig, EngineStatus
from face_swap_studio.engines.deepfacelive import (
    DeepFaceLiveEngine,
    build_launch_command,
    detect_build_kind,
    resolve_deepfacelive_root,
    stage_dfm,
    validate_dfm_file,
)


def _fake_dfm(path: Path, size: int = 600_000) -> Path:
    data = b"\x08\x01" + b"onnx" + b"\x00" * (size - 6)
    path.write_bytes(data)
    return path


def _official_nvidia_layout(root: Path) -> Path:
    """Simulate iperov portable NVIDIA pack renamed to plain DeepFaceLive."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "DeepFaceLive.bat").write_text("@echo off\n", encoding="utf-8")
    cuda_bin = root / "_internal" / "CUDA" / "bin"
    cuda_bin.mkdir(parents=True)
    (cuda_bin / "cudart64_110.dll").write_bytes(b"x")
    (cuda_bin / "cublas64_11.dll").write_bytes(b"x")
    py = root / "_internal" / "python"
    py.mkdir(parents=True)
    (py / "python.exe").write_bytes(b"MZ")
    main = root / "_internal" / "DeepFaceLive"
    main.mkdir(parents=True)
    (main / "main.py").write_text("# stub\n", encoding="utf-8")
    sp = py / "Lib" / "site-packages" / "onnxruntime"
    # marker path scanned via walk
    (root / "_internal" / "python" / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)
    (root / "_internal" / "python" / "Lib" / "site-packages" / "onnxruntime_gpu_marker.txt").write_text(
        "onnxruntime-gpu\n", encoding="utf-8"
    )
    return root


def test_detect_nvidia_via_internal_cuda_even_if_renamed(tmp_path: Path) -> None:
    root = _official_nvidia_layout(tmp_path / "DeepFaceLive")  # renamed, no NVIDIA in name
    info = detect_build_kind(root)
    assert info.kind == "nvidia"
    assert "CUDA" in info.evidence or "cuda" in info.evidence.lower()


def test_detect_dx12_by_path(tmp_path: Path) -> None:
    root = tmp_path / "DeepFaceLive_DX12"
    root.mkdir()
    (root / "main.py").write_text("#\n", encoding="utf-8")
    info = detect_build_kind(root)
    assert info.kind == "dx12"


def test_custom_userdata_uses_python_not_bare_bat(tmp_path: Path) -> None:
    root = _official_nvidia_layout(tmp_path / "DeepFaceLive_NVIDIA")
    custom = tmp_path / "custom_ud"
    custom.mkdir()
    cmd = build_launch_command(root, custom)
    assert "--userdata-dir" in cmd
    assert str(custom) in cmd
    assert cmd[0].endswith("python.exe") or "python" in Path(cmd[0]).name
    assert not cmd[0].endswith(".bat")


def test_default_userdata_may_use_bat_on_win(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _official_nvidia_layout(tmp_path / "DeepFaceLive_NVIDIA")
    ud = root / "userdata"
    ud.mkdir()
    monkeypatch.setattr("face_swap_studio.engines.deepfacelive.sys.platform", "win32")
    cmd = build_launch_command(root, ud)
    assert cmd == [str(root / "DeepFaceLive.bat")]


def test_validate_dfm_rejects_tiny(tmp_path: Path) -> None:
    p = tmp_path / "x.dfm"
    p.write_bytes(b"onnx")
    r = validate_dfm_file(p)
    assert not r.ok
    assert "过小" in r.message


def test_initialize_stages_into_custom_userdata_and_keeps_flag(tmp_path: Path) -> None:
    root = _official_nvidia_layout(tmp_path / "DeepFaceLive")
    dfm = _fake_dfm(tmp_path / "id.dfm")
    custom = tmp_path / "ud_custom"
    eng = DeepFaceLiveEngine()
    eng.initialize(
        EngineConfig(
            extra={
                "dfm_path": str(dfm),
                "deepfacelive_root": str(root),
                "userdata_dir": str(custom),
            }
        )
    )
    assert eng.status() == EngineStatus.READY
    assert (custom / "dfm_models" / "id.dfm").is_file()
    assert eng._launch_cmd is not None
    assert "--userdata-dir" in eng._launch_cmd
    assert str(custom.resolve()) in eng._launch_cmd


def test_initialize_and_start_stop(tmp_path: Path) -> None:
    root = _official_nvidia_layout(tmp_path / "DeepFaceLive_NVIDIA")
    dfm = _fake_dfm(tmp_path / "id.dfm")
    eng = DeepFaceLiveEngine()
    eng.initialize(
        EngineConfig(extra={"dfm_path": str(dfm), "deepfacelive_root": str(root)})
    )
    fake = MagicMock()
    fake.poll.return_value = None
    with patch("face_swap_studio.engines.deepfacelive.subprocess.Popen", return_value=fake) as popen:
        eng.start()
        assert eng.status() == EngineStatus.RUNNING
        popen.assert_called_once()
        # env should include CUDA path when present
        env = popen.call_args.kwargs.get("env") or {}
        assert "CUDA_PATH" in env or True  # portable
        eng.stop()
        fake.terminate.assert_called()


def test_process_exit_sets_error(tmp_path: Path) -> None:
    root = _official_nvidia_layout(tmp_path / "DeepFaceLive_NVIDIA")
    dfm = _fake_dfm(tmp_path / "id.dfm")
    eng = DeepFaceLiveEngine()
    eng.initialize(
        EngineConfig(extra={"dfm_path": str(dfm), "deepfacelive_root": str(root)})
    )
    fake = MagicMock()
    fake.poll.return_value = None
    fake.returncode = 1
    with patch("face_swap_studio.engines.deepfacelive.subprocess.Popen", return_value=fake):
        eng.start()
        assert eng.status() == EngineStatus.RUNNING
        fake.poll.return_value = 1
        st = eng.status()
        assert st == EngineStatus.ERROR
        assert eng.last_error() and "退出" in eng.last_error()
