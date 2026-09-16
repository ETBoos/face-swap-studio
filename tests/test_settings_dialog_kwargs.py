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
        facefusion_root="",
        deepfacelive_root="",
    )
    vals = dlg.values()
    assert vals["width"] == 1280
    assert "dfm_path" not in vals  # dialog only returns its own keys
