"""环境监测 decides whether Instant deps are already present."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from face_swap_studio.core.env_check import (
    CommandResult,
    apply_ready_environment,
    assess_instant_environment,
)


def _dlc(root: Path) -> Path:
    (root / "modules").mkdir(parents=True)
    (root / "run.py").write_text("print('dlc')\n", encoding="utf-8")
    (root / "modules" / "core.py").write_text("# core\n", encoding="utf-8")
    py = root / "venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (root / "models").mkdir()
    (root / "models" / "inswapper_128_fp16.onnx").write_bytes(b"onnx")
    return root


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEP_LIVE_CAM_ROOT", raising=False)
    monkeypatch.delenv("DLC_ROOT", raising=False)
    monkeypatch.delenv("DEEP_LIVE_CAM_PYTHON", raising=False)
    monkeypatch.delenv("DLC_PYTHON", raising=False)


def _runner(argv: list[str]) -> CommandResult:
    text = " ".join(argv)
    if "version_info" in text:
        return CommandResult(0, "3 12\n")
    if any(f"import {name}" in text for name in ("insightface", "cv2", "onnxruntime")):
        return CommandResult(0)
    return CommandResult(1, stderr="unexpected")


def test_ready_checkout_is_recorded_without_clobbering_pro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    monkeypatch.setattr(sys, "version_info", (3, 12, 0, "final", 0))
    root = _dlc(tmp_path / "Deep-Live-Cam")
    monkeypatch.setenv("DEEP_LIVE_CAM_ROOT", str(root))
    settings = {
        "deeplivecam_root": "",
        "engine": "deepfacelive",
        "work_mode": "pro",
        "dfm_path": r"D:\models\actor.dfm",
    }
    report = assess_instant_environment(settings, runner=_runner)
    assert report.ready
    assert "已有" in report.summary_zh()
    assert apply_ready_environment(settings, report) is True
    assert settings["deeplivecam_root"] == str(root.resolve())
    assert settings["deeplivecam_python"].endswith("python")
    assert settings["engine"] == "deepfacelive"
    assert settings["work_mode"] == "pro"
    assert settings["dfm_path"] == r"D:\models\actor.dfm"


def test_missing_insightface_is_not_ready_and_does_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    monkeypatch.setattr(sys, "version_info", (3, 12, 0, "final", 0))
    root = _dlc(tmp_path / "Deep-Live-Cam")
    monkeypatch.setenv("DLC_ROOT", str(root))

    def runner(argv: list[str]) -> CommandResult:
        text = " ".join(argv)
        if "version_info" in text:
            return CommandResult(0, "3 12\n")
        if "import insightface" in text:
            return CommandResult(1, stderr="ModuleNotFoundError: insightface")
        if "import cv2" in text or "import onnxruntime" in text:
            return CommandResult(0)
        return CommandResult(1, stderr="unexpected")

    settings = {"deeplivecam_root": ""}
    report = assess_instant_environment(settings, runner=runner)
    assert report.ready is False
    item = next(i for i in report.items if i.key == "insightface")
    assert item.ok is False
    assert apply_ready_environment(settings, report) is False
    assert settings["deeplivecam_root"] == ""


def test_present_model_is_ok_and_missing_model_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    monkeypatch.setattr(sys, "version_info", (3, 12, 0, "final", 0))
    root = _dlc(tmp_path / "Deep-Live-Cam")
    monkeypatch.setenv("DEEP_LIVE_CAM_ROOT", str(root))
    ready = assess_instant_environment({}, runner=_runner)
    assert next(i for i in ready.items if i.key == "model").ok is True
    (root / "models" / "inswapper_128_fp16.onnx").unlink()
    missing = assess_instant_environment({}, runner=_runner)
    assert missing.ready is False
    assert next(i for i in missing.items if i.key == "model").ok is False


def test_explicit_bad_path_does_not_fall_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    root = _dlc(tmp_path / "Deep-Live-Cam")
    monkeypatch.setenv("DEEP_LIVE_CAM_ROOT", str(root))
    report = assess_instant_environment({"deeplivecam_root": str(tmp_path / "nope")})
    assert report.deeplivecam_root == ""
    assert report.ready is False
    assert next(i for i in report.items if i.key == "dlc").ok is False
