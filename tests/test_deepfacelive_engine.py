"""Unit tests for DeepFaceLive Pro adapter (no real DFL install required)."""

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
    # Minimal ONNX-ish fingerprint for preflight
    data = b"\x08\x01" + b"onnx" + b"\x00" * (size - 6)
    path.write_bytes(data)
    return path


def test_resolve_root_from_explicit(tmp_path: Path) -> None:
    (tmp_path / "DeepFaceLive.bat").write_text("@echo off\n", encoding="utf-8")
    assert resolve_deepfacelive_root(str(tmp_path)) == tmp_path.resolve()


def test_detect_nvidia_by_path(tmp_path: Path) -> None:
    root = tmp_path / "DeepFaceLive_NVIDIA"
    root.mkdir()
    (root / "DeepFaceLive.bat").write_text("@echo off\n", encoding="utf-8")
    info = detect_build_kind(root)
    assert info.kind == "nvidia"


def test_detect_dx12_by_path(tmp_path: Path) -> None:
    root = tmp_path / "DeepFaceLive_DX12"
    root.mkdir()
    (root / "main.py").write_text("#\n", encoding="utf-8")
    info = detect_build_kind(root)
    assert info.kind == "dx12"


def test_validate_dfm_rejects_tiny(tmp_path: Path) -> None:
    p = tmp_path / "x.dfm"
    p.write_bytes(b"onnx")
    r = validate_dfm_file(p)
    assert not r.ok
    assert "过小" in r.message


def test_validate_dfm_ok(tmp_path: Path) -> None:
    p = _fake_dfm(tmp_path / "ok.dfm")
    r = validate_dfm_file(p)
    assert r.ok


def test_stage_dfm_copies(tmp_path: Path) -> None:
    dfm = _fake_dfm(tmp_path / "face.dfm")
    ud = tmp_path / "userdata"
    dest = stage_dfm(dfm, ud)
    assert dest == ud / "dfm_models" / "face.dfm"
    assert dest.stat().st_size == dfm.stat().st_size


def test_build_launch_command_main_py(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("# stub\n", encoding="utf-8")
    ud = tmp_path / "userdata"
    ud.mkdir()
    cmd = build_launch_command(tmp_path, ud, no_cuda=True)
    assert "main.py" in cmd[1]
    assert "DeepFaceLive" in cmd
    assert "--userdata-dir" in cmd
    assert "--no-cuda" in cmd


def test_initialize_rejects_dx12(tmp_path: Path) -> None:
    root = tmp_path / "DeepFaceLive_DX12"
    root.mkdir()
    (root / "DeepFaceLive.bat").write_text("@echo off\n", encoding="utf-8")
    dfm = _fake_dfm(tmp_path / "id.dfm")
    eng = DeepFaceLiveEngine()
    with pytest.raises(RuntimeError, match="DX12"):
        eng.initialize(
            EngineConfig(
                extra={
                    "dfm_path": str(dfm),
                    "deepfacelive_root": str(root),
                }
            )
        )


def test_initialize_and_start_mocked(tmp_path: Path) -> None:
    root = tmp_path / "DeepFaceLive_NVIDIA"
    root.mkdir()
    (root / "DeepFaceLive.bat").write_text("@echo off\n", encoding="utf-8")
    (root / "main.py").write_text("# stub\n", encoding="utf-8")
    (root / "cudnn64_8.dll").write_bytes(b"x")
    dfm = _fake_dfm(tmp_path / "id.dfm")

    eng = DeepFaceLiveEngine()
    eng.initialize(
        EngineConfig(
            extra={
                "dfm_path": str(dfm),
                "deepfacelive_root": str(root),
            }
        )
    )
    assert eng.status() == EngineStatus.READY
    assert (root / "userdata" / "dfm_models" / "id.dfm").is_file()

    fake = MagicMock()
    fake.poll.return_value = None
    with patch("face_swap_studio.engines.deepfacelive.subprocess.Popen", return_value=fake) as popen:
        eng.start()
        assert eng.status() == EngineStatus.RUNNING
        popen.assert_called_once()
        eng.stop()
        fake.terminate.assert_called()
