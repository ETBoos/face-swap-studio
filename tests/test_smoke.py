"""Unit / smoke tests that do not require a display or GPU."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


def test_version():
    from face_swap_studio import __version__

    assert __version__ == "0.2.0a1"


def test_consent_banner():
    from face_swap_studio.core.consent import BANNER_ZH, CONSENT_CHECKLIST_ZH, checklist_text

    assert "授权" in BANNER_ZH
    assert len(CONSENT_CHECKLIST_ZH) >= 3
    assert "授权确认清单" in checklist_text()


def test_project_store(tmp_path: Path):
    from face_swap_studio.core.project import ProjectStore

    store = ProjectStore(tmp_path)
    meta = store.create("测试项目")
    assert meta.name == "测试项目" or "测试" in meta.name
    assert (tmp_path / meta.name / "project.json").exists()
    # asset
    img = tmp_path / "face.png"
    # minimal PNG via numpy + cv2 if available, else write bytes stub file
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    meta = store.add_asset(meta, img, label="演员A", consent_confirmed=True)
    assert len(meta.assets) == 1
    loaded = store.load(meta.name)
    assert loaded.assets[0]["label"] == "演员A"


def test_usage_log(tmp_path: Path):
    from face_swap_studio.core.usage_log import UsageLog

    log = UsageLog(tmp_path / "usage.jsonl")
    log.record("test_event", foo=1)
    text = (tmp_path / "usage.jsonl").read_text(encoding="utf-8")
    assert "test_event" in text


def test_placeholder_engine_synthetic():
    from face_swap_studio.engines.base import EngineConfig
    from face_swap_studio.engines.placeholder import PlaceholderEngine

    eng = PlaceholderEngine()
    caps = eng.capabilities()
    assert caps.is_stub is True
    # Use unlikely camera index so we fall back to synthetic slate
    eng.initialize(EngineConfig(camera_index=99, width=320, height=240))
    eng.start()
    frame = eng.read_frame()
    assert frame is not None
    assert frame.image.shape == (240, 320, 3)
    assert frame.meta.get("stub") is True
    eng.shutdown()


def test_dfl_requires_dfm():
    from face_swap_studio.engines.base import EngineConfig
    from face_swap_studio.engines.deepfacelive import DeepFaceLiveEngine, create_engine

    eng = DeepFaceLiveEngine()
    assert eng.capabilities().name == "deepfacelive"
    with pytest.raises(RuntimeError, match="dfm"):
        eng.initialize(EngineConfig())

    ph = create_engine("placeholder")
    assert ph.capabilities().name == "Placeholder"
