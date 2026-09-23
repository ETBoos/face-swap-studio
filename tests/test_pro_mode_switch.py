"""专模 selects DeepFaceLive (.dfm), and switching modes shuts the previous engine down."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from face_swap_studio.engines.base import EngineConfig
from face_swap_studio.engines.config_builder import build_engine_config
from face_swap_studio.engines.deepfacelive import DeepFaceLiveEngine, create_engine
from face_swap_studio.engines.deeplivecam import DeepLiveCamEngine
from face_swap_studio.engines.facefusion_stub import FaceFusionStubEngine
from face_swap_studio.engines.modes import MODE_ENGINE_IDS, WorkMode


def test_pro_mode_routes_to_deepfacelive_not_facefusion_or_dlc():
    pro = create_engine(MODE_ENGINE_IDS[WorkMode.PRO])
    assert isinstance(pro, DeepFaceLiveEngine)
    assert pro.capabilities().name == "deepfacelive"
    assert pro.capabilities().is_stub is False
    assert not isinstance(pro, (FaceFusionStubEngine, DeepLiveCamEngine))
    assert isinstance(create_engine("pro"), DeepFaceLiveEngine)
    assert isinstance(create_engine("dfl"), DeepFaceLiveEngine)

    instant = create_engine(MODE_ENGINE_IDS[WorkMode.SIMPLE])
    assert isinstance(instant, DeepLiveCamEngine)
    assert instant.capabilities().name == "deeplivecam"
    assert instant.capabilities().is_stub is False
    # Legacy id stays on the instant path and must not construct the FaceFusion stub.
    legacy = create_engine("facefusion")
    assert isinstance(legacy, DeepLiveCamEngine)
    assert not isinstance(legacy, FaceFusionStubEngine)


def test_pro_config_keeps_dfm_root_and_userdata():
    cfg = build_engine_config(
        {
            "work_mode": WorkMode.PRO.value,
            "engine": "deepfacelive",
            "dfm_path": r"D:\models\actor.dfm",
            "deepfacelive_root": r"D:\DeepFaceLive_NVIDIA",
            "userdata_dir": r"D:\dfl-userdata",
            "facefusion_root": r"D:\FaceFusion",
        }
    )
    assert cfg.extra["dfm_path"] == r"D:\models\actor.dfm"
    assert cfg.extra["deepfacelive_root"] == r"D:\DeepFaceLive_NVIDIA"
    assert cfg.extra["userdata_dir"] == r"D:\dfl-userdata"
    # facefusion_root is not a 专模 extra key and must not be required to launch.
    assert "facefusion_root" not in cfg.extra
    eng = create_engine("deepfacelive")
    assert eng.capabilities().name == "deepfacelive"
    with pytest.raises(RuntimeError, match="专模"):
        eng.initialize(EngineConfig())


pytest.importorskip("PySide6")

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from face_swap_studio.licensing.plans import PlanTier
from face_swap_studio.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


class _Probe:
    def __init__(self) -> None:
        self.shutdown_calls = 0
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1

    def shutdown(self) -> None:
        self.shutdown_calls += 1


def _activate_pro(window: MainWindow) -> None:
    window.license.apply_usdt_payment_callback(
        txid="protxid01",
        network="TRC20",
        amount_usdt=599,
        tier=PlanTier.PRO,
    )


def test_mode_switch_shuts_down_previous_engine_and_clears_preview(qapp, tmp_path, monkeypatch):
    prompts: list[tuple] = []

    def _info(*args, **kwargs):
        prompts.append(args)

    monkeypatch.setattr(QMessageBox, "information", _info)
    window = MainWindow(projects_root=tmp_path / "projects")
    try:
        probe = _Probe()
        window.engine = probe
        image = QImage(8, 8, QImage.Format.Format_RGB888)
        image.fill(0x112233)
        window.preview_label.setPixmap(QPixmap.fromImage(image))
        assert window.preview_label.pixmap() is not None
        assert not window.preview_label.pixmap().isNull()

        pro_idx = window.mode_combo.findData(WorkMode.PRO.value)
        assert pro_idx >= 0
        window.mode_combo.setCurrentIndex(pro_idx)

        assert probe.shutdown_calls == 1
        assert window.settings["work_mode"] == "pro"
        assert window.settings["engine"] == "deepfacelive"
        assert isinstance(window.engine, DeepFaceLiveEngine)
        assert window._resolve_engine_name() == "deepfacelive"
        assert window.btn_dfm.isEnabled() is False
        assert "专模" in window.preview_caption.text()
        assert window.preview_label.pixmap() is None or window.preview_label.pixmap().isNull()
        assert prompts and "专模" in prompts[-1][2]
        # Stale FaceFusion id must not pull start off DeepFaceLive.
        window.settings["engine"] = "facefusion"
        assert window._resolve_engine_name() == "deepfacelive"
        window.settings["engine"] = "deepfacelive"

        dfl = window.engine
        shutdowns = {"n": 0}
        original = dfl.shutdown

        def _wrapped() -> None:
            shutdowns["n"] += 1
            original()

        dfl.shutdown = _wrapped  # type: ignore[method-assign]
        window.mode_combo.setCurrentIndex(window.mode_combo.findData(WorkMode.SIMPLE.value))
        assert shutdowns["n"] == 1
        assert isinstance(window.engine, DeepLiveCamEngine)
        assert window.settings["engine"] == "deeplivecam"
        assert window._resolve_engine_name() == "deeplivecam"
        assert "即用" in window.preview_caption.text()
    finally:
        window.close()


def test_pro_start_requires_dfm_and_keeps_deepfacelive(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "face_swap_studio.ui.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: ("", ""),
    )
    notes: list[tuple] = []
    monkeypatch.setattr(
        "face_swap_studio.ui.main_window.QMessageBox.information",
        lambda *args, **kwargs: notes.append(args),
    )
    window = MainWindow(projects_root=tmp_path / "projects")
    try:
        _activate_pro(window)
        window.mode_combo.setCurrentIndex(window.mode_combo.findData(WorkMode.PRO.value))
        assert window.btn_dfm.isEnabled() is True
        assert isinstance(window.engine, DeepFaceLiveEngine)
        window._start_preview()
        assert window._previewing is False
        assert any(len(args) > 1 and args[1] == "需要 .dfm" for args in notes)
        assert isinstance(window.engine, DeepFaceLiveEngine)
        assert not isinstance(window.engine, DeepLiveCamEngine)

        dfm = tmp_path / "actor.dfm"
        dfm.write_bytes(b"tiny")
        root = tmp_path / "DeepFaceLive_NVIDIA"
        ud = tmp_path / "userdata"
        window.settings["dfm_path"] = str(dfm)
        window.settings["deepfacelive_root"] = str(root)
        window.settings["userdata_dir"] = str(ud)
        cfg = build_engine_config(
            window.settings,
            source_face_paths=window._source_face_paths(),
            watermark_text=None,
        )
        assert cfg.extra["dfm_path"] == str(dfm)
        assert cfg.extra["deepfacelive_root"] == str(root)
        assert cfg.extra["userdata_dir"] == str(ud)
        assert "deeplivecam_root" not in cfg.extra

        crits: list[tuple] = []
        monkeypatch.setattr(
            "face_swap_studio.ui.main_window.QMessageBox.critical",
            lambda *args, **kwargs: crits.append(args),
        )
        window._start_preview()
        assert window._previewing is False
        assert crits
        message = str(crits[-1][2])
        assert "Deep-Live-Cam" not in message
        assert "专模" in message or "dfm" in message.lower()
        assert isinstance(window.engine, DeepFaceLiveEngine)
    finally:
        window.close()
