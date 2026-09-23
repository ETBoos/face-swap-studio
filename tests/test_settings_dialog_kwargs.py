"""Item 1: SettingsDialog must accept full settings dict without TypeError."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from face_swap_studio.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def test_settings_dialog_ignores_unknown_keys(qapp):
    dlg = SettingsDialog(
        None,
        width=1280,
        height=720,
        camera_index=0,
        gpu_device="cuda:0",
        engine="placeholder",
        work_mode="simple",
        dfm_path="/tmp/x.dfm",
        facefusion_root=r"D:\FaceFusion",
        deepfacelive_root="",
    )
    vals = dlg.values()
    assert vals["width"] == 1280
    assert "work_mode" not in vals
    assert "facefusion_root" not in vals
    assert vals["dfm_path"] == "/tmp/x.dfm"
    assert vals["deepfacelive_root"] == ""
    assert vals["userdata_dir"] == ""
    assert vals["dlc_session"] == "preview"
    assert "deeplivecam_root" in vals


def test_settings_dialog_roundtrips_pro_keys(qapp):
    dlg = SettingsDialog(
        None,
        width=1920,
        height=1080,
        camera_index=1,
        gpu_device="cuda:0",
        engine="deepfacelive",
        dfm_path=r"D:\models\actor.dfm",
        deepfacelive_root=r"D:\DeepFaceLive_NVIDIA",
        userdata_dir=r"D:\dfl-userdata",
        facefusion_root=r"D:\FaceFusion",
    )
    assert dlg.engine_combo.currentData() == "deepfacelive"
    vals = dlg.values()
    assert vals["engine"] == "deepfacelive"
    assert vals["dfm_path"] == r"D:\models\actor.dfm"
    assert vals["deepfacelive_root"] == r"D:\DeepFaceLive_NVIDIA"
    assert vals["userdata_dir"] == r"D:\dfl-userdata"
    assert "facefusion_root" not in vals


def test_main_window_defaults_to_instant_dlc(qapp, tmp_path):
    from face_swap_studio.ui.main_window import MainWindow

    window = MainWindow(projects_root=tmp_path)
    try:
        assert "即用" in window.mode_combo.itemText(0)
        assert "Deep-Live-Cam" in window.mode_combo.itemText(0)
        assert "专模" in window.mode_combo.itemText(1)
        assert "DeepFaceLive" in window.mode_combo.itemText(1)
        assert window.settings["work_mode"] == "simple"
        assert window.settings["engine"] == "deeplivecam"
        assert window.session_combo.currentData() == "preview"
        assert window.btn_dfm.isEnabled() is False
        assert window.btn_face.isEnabled() is True
    finally:
        window.close()
