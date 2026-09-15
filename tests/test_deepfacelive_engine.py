"""Unit tests for DeepFaceLive Pro adapter (no real DFL install required)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from face_swap_studio.engines.base import EngineConfig, EngineStatus
from face_swap_studio.engines.deepfacelive import (
    DeepFaceLiveEngine,
    build_launch_command,
    resolve_deepfacelive_root,
    stage_dfm,
)


def test_resolve_root_from_explicit(tmp_path: Path) -> None:
    (tmp_path / "DeepFaceLive.bat").write_text("@echo off\n", encoding="utf-8")
    assert resolve_deepfacelive_root(str(tmp_path)) == tmp_path.resolve()


def test_stage_dfm_copies(tmp_path: Path) -> None:
    dfm = tmp_path / "face.dfm"
    dfm.write_bytes(b"dfm-bytes")
    ud = tmp_path / "userdata"
    dest = stage_dfm(dfm, ud)
    assert dest == ud / "dfm_models" / "face.dfm"
    assert dest.read_bytes() == b"dfm-bytes"


def test_build_launch_command_main_py(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("# stub\n", encoding="utf-8")
    ud = tmp_path / "userdata"
    ud.mkdir()
    cmd = build_launch_command(tmp_path, ud, no_cuda=True)
    assert "main.py" in cmd[1]
    assert "DeepFaceLive" in cmd
    assert "--userdata-dir" in cmd
    assert "--no-cuda" in cmd


def test_initialize_requires_dfm(tmp_path: Path) -> None:
    eng = DeepFaceLiveEngine()
    with pytest.raises(RuntimeError, match="dfm"):
        eng.initialize(EngineConfig(extra={}))


def test_initialize_and_start_mocked(tmp_path: Path) -> None:
    (tmp_path / "DeepFaceLive.bat").write_text("@echo off\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("# stub\n", encoding="utf-8")
    dfm = tmp_path / "id.dfm"
    dfm.write_bytes(b"x")

    eng = DeepFaceLiveEngine()
    eng.initialize(
        EngineConfig(
            extra={
                "dfm_path": str(dfm),
                "deepfacelive_root": str(tmp_path),
            }
        )
    )
    assert eng.status() == EngineStatus.READY
    assert (tmp_path / "userdata" / "dfm_models" / "id.dfm").is_file()

    fake = MagicMock()
    fake.poll.return_value = None
    with patch("face_swap_studio.engines.deepfacelive.subprocess.Popen", return_value=fake) as popen:
        eng.start()
        assert eng.status() == EngineStatus.RUNNING
        popen.assert_called_once()
        eng.stop()
        fake.terminate.assert_called()
