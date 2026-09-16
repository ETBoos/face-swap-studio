"""Real Qt user-flow checks with deterministic engines; no cameras or GPU required."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from face_swap_studio.engines.base import EngineFrame
from face_swap_studio.ui.main_window import MainWindow


class FakeEngine:
    def __init__(self, *, stub=False, external=False):
        self.stub = stub
        self.external = external
        self.state = "starting"
        self.frames = []
        self.shutdown_calls = 0
        self.initialized = False
        self.start_calls = 0
        self.error = "测试引擎已退出"

    def initialize(self, cfg):
        self.cfg = cfg
        self.initialized = True

    def start(self):
        self.start_calls += 1

    def shutdown(self):
        self.shutdown_calls += 1

    def status(self):
        return self.state

    def last_error(self):
        return self.error

    def capabilities(self):
        return SimpleNamespace(
            is_stub=self.stub, preview_mode="external" if self.external else "internal"
        )

    def read_frame(self):
        return self.frames.pop(0) if self.frames else None

    def push(self, *, real=True, frame_id=1):
        self.state = "running"
        self.frames.append(
            EngineFrame(
                np.zeros((240, 320, 3), dtype=np.uint8),
                fps=25,
                meta={
                    "stub": self.stub,
                    "face_swapped": real,
                    "safe_to_output": real,
                    "frame_id": frame_id,
                    "reason": "没有检测到人脸",
                },
            )
        )


class FakeOutput:
    def __init__(self):
        self.state = "stopped"
        self.sent = []
        self.starts = 0
        self.stops = 0
        self.error = ""
        self.device = "Test virtual camera"

    def status(self):
        return self.state

    def start(self, w, h, fps):
        self.starts += 1
        self.state = "running"

    def send(self, frame):
        self.sent.append(frame)
        return True

    def pause(self, reason):
        self.state = "paused"
        self.error = reason

    def stop(self):
        self.state = "stopped"
        self.stops += 1

    def last_error(self):
        return self.error


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def until(condition, timeout=2):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert condition()


@pytest.fixture
def scene(qapp, tmp_path):
    engines, outputs = [], []
    now = [100.0]

    def factory(name):
        eng = FakeEngine(stub=name == "placeholder", external=name == "deepfacelive")
        engines.append(eng)
        return eng

    def output_factory():
        out = FakeOutput()
        outputs.append(out)
        return out

    window = MainWindow(
        tmp_path / "projects",
        engine_factory=factory,
        output_factory=output_factory,
        clock=lambda: now[0],
    )
    photo = tmp_path / "face.png"
    cv2.imencode(".png", np.ones((64, 64, 3), dtype=np.uint8) * 100)[1].tofile(photo)
    yield window, engines, outputs, now, photo
    window.close()
    QTest.qWait(20)


def begin(scene):
    w, engines, _, _, photo = scene
    assert w._select_photo(str(photo))
    w.consent_box.setChecked(True)
    w.btn_start.click()
    until(lambda: not w._starting_job)
    w._timer.stop()  # explicit deterministic ticks below
    return w, engines[-1]


def test_default_mode_is_consistent_and_no_engine_or_camera_opens(scene, monkeypatch):
    w, engines, outputs, _, _ = scene
    assert not engines and not outputs
    assert w.mode_combo.currentData() == "simple"
    assert w.settings["engine"] == "facefusion"
    assert w.session_state == "idle"
    assert not w.btn_output_start.isEnabled()


def test_photo_without_project_and_settings_survive_restart(scene, qapp):
    w, _, _, _, photo = scene
    assert w._select_photo(str(photo))
    w.consent_box.setChecked(True)
    w.mode_combo.setCurrentIndex(w.mode_combo.findData("demo"))
    path = w.store.root
    w.close()
    restored = MainWindow(path)
    try:
        assert restored.current is None
        assert restored._asset_paths() == [str(photo)]
        assert restored.settings["work_mode"] == "demo"
        assert restored.settings["engine"] == "placeholder"
        assert restored.mode_combo.currentData() == "demo"
        assert restored.consent_box.isChecked()
        assert restored.engine is None
    finally:
        restored.close()


def test_first_real_frame_gates_output_and_loss_of_face_pauses(scene):
    w, eng = begin(scene)
    assert w.session_state == "waiting"
    assert not w.btn_output_start.isEnabled()
    eng.push(frame_id=1)
    w._on_tick()
    assert w.session_state == "previewing"
    assert w.btn_output_start.isEnabled()
    assert w.output is None  # first frame must never auto-start broadcasting
    w.btn_output_start.click()
    eng.push(frame_id=2)
    w._on_tick()
    assert len(w.output.sent) == 2
    eng.push(real=False, frame_id=3)
    w._on_tick()
    assert w.output.state == "paused"
    assert len(w.output.sent) == 2
    assert not w.btn_output_start.isEnabled()
    eng.push(frame_id=4)
    w._on_tick()
    assert w.btn_output_start.isEnabled()
    assert w.output.state == "paused"  # recovery needs user's explicit restart
    w.btn_output_start.click()
    assert w.output.state == "running"
    assert len(w.output.sent) == 3


def test_demo_cannot_output_even_when_frame_claims_safe(scene):
    w, _, _, _, _ = scene
    w.mode_combo.setCurrentIndex(w.mode_combo.findData("demo"))
    w.btn_start.click()
    until(lambda: not w._starting_job)
    w._timer.stop()
    w.engine.push()
    w._on_tick()
    assert w.session_state == "demo"
    assert not w.btn_output_start.isEnabled()
    w._start_output()
    assert w.output is None


def test_exit_recovers_start_button_and_clears_stale_frame(scene):
    w, eng = begin(scene)
    eng.push()
    w._on_tick()
    w.btn_output_start.click()
    eng.state = "error"
    w._on_tick()
    assert w.session_state == "error"
    assert w.btn_start.isEnabled()
    assert not w.btn_stop.isEnabled()
    assert w._last_frame is None
    assert w.output.state == "stopped"
    assert "测试引擎已退出" in w.notice_label.text()
    until(lambda: eng.shutdown_calls == 1)


def test_first_frame_timeout_is_recoverable(scene):
    w, _ = begin(scene)
    scene[3][0] += w.settings["facefusion_startup_timeout"] + 1
    w._on_tick()
    assert w.session_state == "error"
    assert w.btn_start.isEnabled()
    assert "首帧" in w.notice_label.text()


def test_stale_stream_pauses_and_cannot_restart_until_new_frame(scene):
    w, eng = begin(scene)
    eng.push()
    w._on_tick()
    w.btn_output_start.click()
    scene[3][0] += 2
    w._on_tick()
    assert w.output.state == "paused"
    assert not w.btn_output_start.isEnabled()
    assert w.session_state == "waiting"


def test_project_change_clears_output_and_frame(scene):
    w, eng = begin(scene)
    eng.push()
    w._on_tick()
    w.btn_output_start.click()
    project = w.store.create("another")
    w._on_project_selected(project.name)
    assert not w._previewing
    assert not w._timer.isActive()
    assert w._last_frame is None
    assert w.output.state == "stopped"
    assert not w.btn_export.isEnabled()
    until(lambda: eng.shutdown_calls == 1)


def test_paid_mode_remains_gated_even_if_engine_setting_is_modified(scene):
    w, engines, _, _, _ = scene
    w.consent_box.setChecked(True)
    w.mode_combo.setCurrentIndex(w.mode_combo.findData("pro"))
    w.settings["dfm_path"] = "fake.dfm"
    w.settings["engine"] = "placeholder"
    w.btn_start.click()
    assert not engines
    assert not w.btn_dfm.isEnabled()
    assert "授权" in w.notice_label.text()


def test_external_window_never_reports_internal_preview(scene, monkeypatch):
    w, engines, _, now, _ = scene
    monkeypatch.setattr(w.license.state, "allows_pro_dfm", lambda: True)
    w.consent_box.setChecked(True)
    w.mode_combo.setCurrentIndex(w.mode_combo.findData("pro"))
    w.settings["dfm_path"] = "fake.dfm"
    w.btn_start.click()
    until(lambda: not w._starting_job)
    w._timer.stop()
    engines[-1].state = "running"
    now[0] += 1000
    w._on_tick()
    assert w.session_state == "external"
    assert "尚未" in w.state_label.text()
    assert not w.btn_output_start.isEnabled()


def test_device_names_arrive_without_opening_camera(scene, monkeypatch):
    w = scene[0]
    opened = []
    monkeypatch.setattr(cv2, "VideoCapture", lambda *a: opened.append(a))
    w._on_devices_found([(0, "USB Camera"), (1, "Webcam HD")], "")
    w.camera_combo.setCurrentIndex(1)
    assert w.settings["camera_index"] == 1
    assert "Webcam HD" in w.settings["camera_name"]
    assert not opened


def test_missing_engine_dependency_gives_recoverable_error(scene):
    w, _, _, _, photo = scene
    eng = FakeEngine()

    def missing(_cfg):
        raise RuntimeError("请准备 FaceFusion 环境：找不到运行程序")

    eng.initialize = missing
    w._factory = lambda _: eng
    assert w._select_photo(str(photo))
    w.consent_box.setChecked(True)
    w.btn_start.click()
    until(lambda: w.session_state == "error")
    assert w.btn_start.isEnabled()
    assert "找不到运行程序" in w.notice_label.text()
    assert str(w.log.path) in w.notice_label.text()


def test_output_backend_missing_keeps_preview_working(scene):
    w, eng = begin(scene)
    eng.push()
    w._on_tick()

    def unavailable():
        raise RuntimeError("请安装 FaceSwap Studio Camera 组件")

    w._output_factory = unavailable
    w.btn_output_start.click()
    assert w.session_state == "previewing"
    assert w.btn_output_start.isEnabled()
    assert "组件" in w.output_info.text()


def test_cancel_during_initialization_never_restarts_old_session(scene):
    import threading

    w, _, _, _, photo = scene
    released = threading.Event()
    entered = threading.Event()
    eng = FakeEngine()

    def initialize(cfg):
        entered.set()
        released.wait(2)

    eng.initialize = initialize
    w._factory = lambda _: eng
    w._select_photo(str(photo))
    w.consent_box.setChecked(True)
    w.btn_start.click()
    until(entered.is_set)
    w.btn_stop.click()
    released.set()
    until(lambda: eng.shutdown_calls == 1)
    QTest.qWait(30)
    assert eng.start_calls == 0
    assert not w._previewing
    assert w.session_state == "idle"
    assert w.engine is None


def test_camera_scan_is_asynchronous_and_does_not_probe_frames(scene, monkeypatch):
    from PySide6.QtMultimedia import QMediaDevices

    w = scene[0]
    captured = []
    monkeypatch.setattr(cv2, "VideoCapture", lambda *args: captured.append(args))
    monkeypatch.setattr(
        QMediaDevices, "videoInputs", lambda: [SimpleNamespace(description=lambda: "Test USB")]
    )
    w.btn_scan.click()
    until(lambda: not w._scan_running)
    assert "Test USB" in w.camera_combo.itemText(0)
    assert not captured


def test_long_session_face_loss_gets_a_fresh_recovery_window(scene):
    w, eng = begin(scene)
    eng.push()
    w._on_tick()
    scene[3][0] += 300
    eng.push(real=False, frame_id=2)
    w._on_tick()
    assert w.session_state == "waiting"
    assert w._previewing
