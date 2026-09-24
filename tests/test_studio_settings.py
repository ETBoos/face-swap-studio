"""Shell settings: detect Deep-Live-Cam and write the path without clobbering Pro."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from face_swap_studio.core.studio_settings import (
    DLC_SETUP_OFFER_ZH,
    default_settings,
    ensure_deeplivecam_root,
    find_setup_all_script,
    launch_setup_script,
    load_settings,
    main,
    probe_deeplivecam_root,
    save_settings,
    write_deeplivecam_root,
)


def _dlc_root(root: Path) -> Path:
    (root / "modules").mkdir(parents=True)
    (root / "run.py").write_text("print('dlc')\n", encoding="utf-8")
    (root / "modules" / "core.py").write_text("# core\n", encoding="utf-8")
    return root


def _clear_dlc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEP_LIVE_CAM_ROOT", raising=False)
    monkeypatch.delenv("DLC_ROOT", raising=False)
    monkeypatch.delenv("FSS_SETTINGS_PATH", raising=False)


def test_probe_prefers_env_over_userprofile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_dlc_env(monkeypatch)
    home = tmp_path / "home"
    user_copy = _dlc_root(home / "Deep-Live-Cam")
    env_copy = _dlc_root(tmp_path / "from-env")
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("DEEP_LIVE_CAM_ROOT", str(env_copy))
    assert probe_deeplivecam_root() == env_copy.resolve()
    assert user_copy.is_dir()


def test_probe_userprofile_when_env_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_dlc_env(monkeypatch)
    home = tmp_path / "home"
    root = _dlc_root(home / "Deep-Live-Cam")
    monkeypatch.setattr(Path, "home", lambda: home)
    assert probe_deeplivecam_root() == root.resolve()


def test_ensure_fills_empty_root_and_keeps_pro_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_dlc_env(monkeypatch)
    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    monkeypatch.setenv("DLC_ROOT", str(root))
    settings = {
        "deeplivecam_root": "",
        "engine": "deepfacelive",
        "work_mode": "pro",
        "dfm_path": r"D:\models\actor.dfm",
    }
    found = ensure_deeplivecam_root(settings)
    assert found == str(root.resolve())
    assert settings["engine"] == "deepfacelive"
    assert settings["work_mode"] == "pro"
    assert settings["dfm_path"] == r"D:\models\actor.dfm"


def test_ensure_does_not_replace_explicit_invalid_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_dlc_env(monkeypatch)
    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    monkeypatch.setenv("DEEP_LIVE_CAM_ROOT", str(root))
    bad = str(tmp_path / "not-dlc")
    settings = {"deeplivecam_root": bad}
    assert ensure_deeplivecam_root(settings) is None
    assert settings["deeplivecam_root"] == bad


def test_write_merges_deeplivecam_root_without_clobbering_pro(tmp_path: Path) -> None:
    dest = tmp_path / "settings.json"
    dest.write_text(
        json.dumps(
            {
                "engine": "deepfacelive",
                "work_mode": "pro",
                "dfm_path": r"D:\models\actor.dfm",
                "deepfacelive_root": r"D:\DeepFaceLive_NVIDIA",
                "userdata_dir": r"D:\dfl-userdata",
                "deeplivecam_root": "",
            }
        ),
        encoding="utf-8",
    )
    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    written = write_deeplivecam_root(str(root), dest)
    data = json.loads(written.read_text(encoding="utf-8"))
    assert data["deeplivecam_root"] == str(root.resolve())
    assert data["engine"] == "deepfacelive"
    assert data["work_mode"] == "pro"
    assert data["dfm_path"] == r"D:\models\actor.dfm"
    assert data["deepfacelive_root"] == r"D:\DeepFaceLive_NVIDIA"
    assert data["userdata_dir"] == r"D:\dfl-userdata"
    assert load_settings(dest)["dfm_path"] == r"D:\models\actor.dfm"


def test_cli_rejects_non_dlc_and_writes_real_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dest = tmp_path / "settings.json"
    assert main(["--deeplivecam-root", str(tmp_path), "--settings", str(dest)]) == 1
    assert not dest.exists()
    err = capsys.readouterr().err
    assert "不是 Deep-Live-Cam" in err

    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    dest.write_text(json.dumps({"engine": "deepfacelive", "dfm_path": "a.dfm"}), encoding="utf-8")
    assert main(["--deeplivecam-root", str(root), "--settings", str(dest)]) == 0
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["deeplivecam_root"] == str(root.resolve())
    assert data["engine"] == "deepfacelive"
    assert data["dfm_path"] == "a.dfm"


def test_defaults_drop_launched_facefusion_root(tmp_path: Path) -> None:
    assert "facefusion_root" not in default_settings()
    dest = tmp_path / "settings.json"
    dest.write_text(json.dumps({"facefusion_root": r"D:\FaceFusion"}), encoding="utf-8")
    loaded = load_settings(dest)
    # Existing files keep the unused key; new defaults must not reintroduce it.
    assert loaded["facefusion_root"] == r"D:\FaceFusion"
    assert "facefusion_root" not in default_settings()


def test_corrupt_settings_do_not_crash(tmp_path: Path) -> None:
    dest = tmp_path / "settings.json"
    dest.write_text("{", encoding="utf-8")
    loaded = load_settings(dest)
    assert loaded["deeplivecam_root"] == ""
    assert loaded["work_mode"] == "simple"
    save_settings({"deeplivecam_root": r"C:\Deep-Live-Cam"}, dest)
    again = load_settings(dest)
    assert again["work_mode"] == "simple"
    assert again["deeplivecam_root"] == r"C:\Deep-Live-Cam"


def test_offer_copy_is_not_the_missing_engine_error() -> None:
    assert "未找到 Deep-Live-Cam" not in DLC_SETUP_OFFER_ZH
    assert "一键安装" in DLC_SETUP_OFFER_ZH
    assert "打开换脸" in DLC_SETUP_OFFER_ZH


def test_setup_script_is_discoverable_and_windows_only() -> None:
    script = find_setup_all_script()
    assert script is not None
    text = script.read_text(encoding="utf-8")
    assert "setup-deeplivecam-cpu-win.bat" in text
    assert "studio_settings" in text
    assert "打开换脸" in text
    shortcut = (script.parent / "create-desktop-shortcut.ps1").read_text(encoding="utf-8")
    assert "0x6253" in shortcut
    assert "0x5F00" in shortcut
    assert "0x6362" in shortcut
    assert "0x8138" in shortcut
    assert "pythonw.exe" in shortcut
    assert "WindowStyle = 7" in shortcut
    assert "-m face_swap_studio" in shortcut
    assert "cmd.exe" not in shortcut
    launcher = (script.parent / "start-win.bat").read_text(encoding="utf-8")
    assert "pythonw.exe" in launcher
    assert 'start ""' in launcher
    assert "uv run" not in launcher
    cpu = (script.parent / "setup-deeplivecam-cpu-win.bat").read_text(encoding="utf-8")
    assert "cp311-cp311" in cpu
    assert "cp312-cp312" in cpu
    assert "cp313-cp313" in cpu
    assert "pypi.tuna.tsinghua.edu.cn" in cpu
    assert "FSS_DLC_NOPAUSE" in cpu
    with pytest.raises(OSError):
        launch_setup_script(script)


pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from face_swap_studio.core.env_check import EnvCheckItem, EnvReport
from face_swap_studio.ui.main_window import MainWindow
from face_swap_studio.ui.settings_dialog import DIALOG_KEYS, SettingsDialog

CODE_1D = "FS-1D-VBQQ-SDRG-VFF8"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def test_main_window_persists_detected_root(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_dlc_env(monkeypatch)
    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    monkeypatch.setenv("DEEP_LIVE_CAM_ROOT", str(root))
    window = MainWindow(projects_root=tmp_path / "projects")
    try:
        assert window.settings["deeplivecam_root"] == str(root.resolve())
        dlg = SettingsDialog(
            None,
            **{k: window.settings[k] for k in DIALOG_KEYS if k in window.settings},
        )
        assert dlg.dlc_root_edit.text() == str(root.resolve())
        dlg.close()
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["deeplivecam_root"] == str(root.resolve())
        assert saved["work_mode"] == "simple"
        window.license.activate_code(CODE_1D)
        window._on_mode_changed()
        assert "目录已就绪" in window.preview_label.text()
        assert str(root.resolve()) in window.preview_label.text()
    finally:
        window.close()


def test_startup_detect_keeps_saved_pro_mode(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_dlc_env(monkeypatch)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    dest = tmp_path / "settings.json"
    dest.write_text(
        json.dumps(
            {
                "engine": "deepfacelive",
                "work_mode": "pro",
                "dfm_path": r"D:\models\actor.dfm",
                "deepfacelive_root": r"D:\DeepFaceLive_NVIDIA",
                "userdata_dir": r"D:\dfl-userdata",
                "deeplivecam_root": "",
            }
        ),
        encoding="utf-8",
    )
    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    monkeypatch.setenv("DEEP_LIVE_CAM_ROOT", str(root))
    window = MainWindow(projects_root=tmp_path / "projects")
    try:
        assert window.settings["work_mode"] == "pro"
        assert window.settings["engine"] == "deepfacelive"
        assert window.settings["dfm_path"] == r"D:\models\actor.dfm"
        assert window.settings["deepfacelive_root"] == r"D:\DeepFaceLive_NVIDIA"
        assert window.settings["deeplivecam_root"] == str(root.resolve())
        saved = json.loads(dest.read_text(encoding="utf-8"))
        assert saved["engine"] == "deepfacelive"
        assert saved["work_mode"] == "pro"
        assert saved["dfm_path"] == r"D:\models\actor.dfm"
        assert saved["userdata_dir"] == r"D:\dfl-userdata"
        assert saved["deeplivecam_root"] == str(root.resolve())
    finally:
        window.close()


def test_start_without_dlc_offers_setup_instead_of_scary_error(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_dlc_env(monkeypatch)
    monkeypatch.setattr(
        "face_swap_studio.ui.main_window.ensure_deeplivecam_root",
        lambda settings: None,
    )
    window = MainWindow(projects_root=tmp_path / "projects")
    try:
        window.license.activate_code(CODE_1D)
        window._sync_activation_ui()
        window.settings["deeplivecam_root"] = ""
        offered: list[bool] = []
        window._offer_dlc_setup = lambda: offered.append(True)  # type: ignore[method-assign]
        crits: list[tuple] = []
        monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: crits.append(args))
        window._start_preview()
        assert offered == [True]
        assert crits == []
        assert window._previewing is False
        assert "未找到 Deep-Live-Cam" not in window.preview_label.text()
    finally:
        window.close()


def test_detected_root_continues_to_source_face_prompt(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_dlc_env(monkeypatch)
    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    monkeypatch.setenv("DLC_ROOT", str(root))
    window = MainWindow(projects_root=tmp_path / "projects")
    try:
        window.license.activate_code(CODE_1D)
        window._sync_activation_ui()
        window.settings["deeplivecam_root"] = ""
        offered: list[bool] = []
        window._offer_dlc_setup = lambda: offered.append(True)  # type: ignore[method-assign]
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: ("", ""))
        notes: list[tuple] = []
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: notes.append(args))
        window._start_preview()
        assert offered == []
        assert window.settings["deeplivecam_root"] == str(root.resolve())
        assert any(len(args) > 1 and args[1] == "需要源脸" for args in notes)
        assert window._previewing is False
    finally:
        window.close()


def test_env_button_writes_ready_path_and_skips_install(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_dlc_env(monkeypatch)
    root = _dlc_root(tmp_path / "Deep-Live-Cam")
    py = root / "venv" / "bin" / "python"
    report = EnvReport(
        items=(EnvCheckItem("python", "Python", True, "3.12"),),
        deeplivecam_root=str(root.resolve()),
        deeplivecam_python=str(py),
    )
    monkeypatch.setattr(
        "face_swap_studio.ui.main_window.assess_instant_environment",
        lambda settings: report,
    )
    window = MainWindow(projects_root=tmp_path / "projects")
    try:
        assert window.btn_env.text() == "环境监测"
        calls: list[str] = []
        window._run_cpu_setup_and_apply = lambda: calls.append("install")  # type: ignore[method-assign]
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
        window.btn_env.click()
        assert calls == []
        assert window.settings["deeplivecam_root"] == str(root.resolve())
        assert window.settings["deeplivecam_python"] == str(py)
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["deeplivecam_root"] == str(root.resolve())
        assert saved.get("work_mode") == "simple"
    finally:
        window.close()


def test_env_button_installs_when_insightface_missing(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_dlc_env(monkeypatch)
    report = EnvReport(
        items=(EnvCheckItem("insightface", "insightface", False, "未安装"),),
    )
    monkeypatch.setattr(
        "face_swap_studio.ui.main_window.assess_instant_environment",
        lambda settings: report,
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window = MainWindow(projects_root=tmp_path / "projects")
    try:
        calls: list[str] = []
        window._run_cpu_setup_and_apply = lambda: calls.append("install")  # type: ignore[method-assign]
        window.btn_env.click()
        assert calls == ["install"]
        assert window.settings.get("deeplivecam_root", "") == ""
    finally:
        window.close()
