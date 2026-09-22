"""Activation gate: locked seats cannot start preview; USDT or a live trial can."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from face_swap_studio.licensing.plans import PlanTier
from face_swap_studio.licensing.store import LicenseStore
from face_swap_studio.ui.main_window import MainWindow

CODE_1D = "FS-1D-VBQQ-SDRG-VFF8"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def test_unactivated_disables_start_and_keeps_activate(qapp, tmp_path, monkeypatch):
    prompts: list[tuple] = []
    monkeypatch.setattr(
        "face_swap_studio.ui.main_window.QInputDialog.getText",
        lambda *args, **kwargs: prompts.append(args) or ("", False),
    )
    window = MainWindow(projects_root=tmp_path / "projects")
    try:
        qapp.processEvents()
        assert prompts == []
        assert window.btn_start.isEnabled() is False
        assert window.btn_export.isEnabled() is False
        assert window.btn_activate.isEnabled() is True
        assert "未激活" in window.statusBar().currentMessage()
    finally:
        window.close()


def test_valid_trial_enables_start(qapp, tmp_path):
    window = MainWindow(projects_root=tmp_path / "projects")
    try:
        window.license.activate_code(CODE_1D)
        window._sync_activation_ui()
        assert window.license.state.active is False
        assert window.license.state.tier == PlanTier.STARTER
        assert window.btn_start.isEnabled() is True
        assert window.btn_activate.isEnabled() is True
    finally:
        window.close()


def test_expired_trial_blocks_preview(qapp, tmp_path, monkeypatch):
    notes: list[tuple] = []
    monkeypatch.setattr(
        "face_swap_studio.ui.main_window.QMessageBox.information",
        lambda *args, **kwargs: notes.append(args),
    )
    lic = tmp_path / "license.json"
    lic.write_text(
        json.dumps(
            {
                "tier": "starter",
                "seats": 1,
                "dfm_enabled": False,
                "usdt_network": "TRC20",
                "payment_address": "",
                "last_txid": "",
                "active": False,
                "activation_code": CODE_1D,
                "activated_at": "2020-01-01T00:00:00+00:00",
                "expires_at": "2020-01-02T00:00:00+00:00",
                "used_codes": [CODE_1D],
            }
        ),
        encoding="utf-8",
    )
    window = MainWindow(projects_root=tmp_path / "projects")
    try:
        assert "trial_expired" in (window.log.path.read_text(encoding="utf-8"))
        assert window.license.state.expires_at == ""
        assert CODE_1D in window.license.state.used_codes
        assert window.license.state.tier == PlanTier.STARTER
        assert window.license.state.active is False
        assert window.btn_start.isEnabled() is False
        assert window.btn_activate.isEnabled() is True
        window._start_preview()
        assert window._previewing is False
        assert notes and notes[-1][1] == "未激活"
    finally:
        window.close()


def test_usdt_unlocks_preview_without_trial_code(qapp, tmp_path):
    root = tmp_path / "projects"
    store = LicenseStore(tmp_path / "license.json")
    store.apply_usdt_payment_callback(
        txid="abc123456789",
        network="TRC20",
        amount_usdt=599,
        tier=PlanTier.PRO,
    )
    window = MainWindow(projects_root=root)
    try:
        assert window.btn_start.isEnabled() is True
        assert window.license.state.allows_pro_dfm() is True
        assert "USDT" in window.statusBar().currentMessage()
    finally:
        window.close()


def test_activate_dialog_rejects_invalid_code(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *args, **kwargs: ("FS-30D-NOPE-NOPE-NOPE", True),
    )
    warnings: list[tuple] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )
    window = MainWindow(projects_root=tmp_path / "projects")
    try:
        window._prompt_activation()
        assert window.btn_start.isEnabled() is False
        assert window.license.state.used_codes == []
        assert warnings
        assert "无效" in str(warnings[-1][2])
    finally:
        window.close()


def test_expired_clock_blocks_running_preview_flag(qapp, tmp_path):
    """A 1-day trial activated in the past cannot start preview."""
    window = MainWindow(projects_root=tmp_path / "projects")
    try:
        past = datetime.now(timezone.utc) - timedelta(days=3)
        window.license.activate_code(CODE_1D, now=past)
        window.license.enforce_startup_gate()
        window._sync_activation_ui()
        assert window.license.state.active is False
        assert window.license.state.tier == PlanTier.STARTER
        assert window.btn_start.isEnabled() is False
        assert CODE_1D in window.license.state.used_codes
    finally:
        window.close()
