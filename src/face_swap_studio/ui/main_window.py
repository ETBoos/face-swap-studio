"""Four-step desktop workflow with explicit preview and output states."""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from face_swap_studio import __version__
from face_swap_studio.core.preferences import MODE_ENGINES, PreferencesStore
from face_swap_studio.core.project import ProjectMeta, ProjectStore
from face_swap_studio.core.usage_log import UsageLog
from face_swap_studio.engines.base import EngineFrame
from face_swap_studio.engines.config_builder import build_engine_config
from face_swap_studio.engines.deepfacelive_stub import create_engine
from face_swap_studio.engines.lifecycle import shutdown_engine
from face_swap_studio.licensing.store import LicenseStore
from face_swap_studio.ui.activation_dialog import ActivationDialog
from face_swap_studio.ui.settings_dialog import DIALOG_KEYS, SettingsDialog


class _Signals(QObject):
    started = Signal(int, object, object)
    devices = Signal(object, str)


def _default_projects_root() -> Path:
    configured = os.environ.get("FSS_DATA_DIR")
    return (
        Path(configured).expanduser() if configured else Path.home() / "FaceSwapStudio"
    ) / "projects"


def _value(state) -> str:
    return str(getattr(state, "value", state)).lower()


class MainWindow(QMainWindow):
    def __init__(
        self,
        projects_root: Path | None = None,
        *,
        engine_factory=None,
        output_factory=None,
        clock=None,
    ):
        super().__init__()
        app = QApplication.instance()
        if app is not None:
            app.setStyle("Fusion")
        self.setStyleSheet("""
            QMainWindow { background: #f1f5f9; }
            QWidget { font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif; font-size: 13px; color: #263448; }
            QGroupBox { background: white; border: 1px solid #dbe3ed; border-radius: 9px; margin-top: 17px; padding: 12px 9px 9px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #334e70; }
            QPushButton { background: #ffffff; border: 1px solid #cdd8e5; border-radius: 6px; padding: 6px 10px; min-height: 22px; }
            QPushButton:hover { background: #eaf2fe; border-color: #87ace1; }
            QPushButton:pressed { background: #dceaff; }
            QPushButton:disabled { color: #8c9aad; background: #edf1f5; border-color: #dce3ea; }
            QPushButton#primaryButton { background: #2563eb; color: white; border: 1px solid #2563eb; font-weight: 600; }
            QPushButton#primaryButton:hover { background: #1d4ed8; }
            QPushButton#primaryButton:disabled { background: #e4ebf4; border-color: #dbe3ed; color: #899ab1; }
            QComboBox, QLineEdit, QSpinBox { background: white; border: 1px solid #cdd8e5; border-radius: 5px; padding: 5px; min-height: 22px; }
            QCheckBox { spacing: 7px; padding: 4px 0; }
            QListWidget { background: white; border: 1px solid #dbe3ed; border-radius: 5px; }
            QScrollArea { border: none; background: #f1f5f9; }
            QWidget#workflowControls { background: #f1f5f9; }
            QStatusBar { background: #e8eef6; color: #4b5d73; padding: 3px; }
        """)
        self.setWindowTitle(f"FaceSwap Studio · 实时通话与直播  v{__version__}")
        self.resize(1200, 850)
        self.setMinimumSize(960, 700)
        self.store = ProjectStore(projects_root or _default_projects_root())
        self.log = UsageLog(self.store.root.parent / "logs" / "usage.jsonl")
        self.preferences = PreferencesStore(self.store.root.parent / "preferences.json")
        self.settings = self.preferences.load()
        self.license = LicenseStore(self.store.root.parent / "license.json")
        self.current: ProjectMeta | None = None
        self._factory = engine_factory or create_engine
        self._output_factory = output_factory
        self._clock = clock or time.monotonic
        self.engine = None
        self.output = None
        self._previewing = False
        self.session_state = "idle"
        self._last_frame: EngineFrame | None = None
        self._last_real_frame: EngineFrame | None = None
        self._last_frame_at = 0.0
        self._started_at = 0.0
        self._last_frame_id = None
        self._generation = 0
        self._starting_job = False
        self._startup_cancel = threading.Event()
        self._cleanup_thread = None
        self._closed = False
        self._scan_running = False
        self._camera_scan_empty = False
        self._signals = _Signals(self)
        self._signals.started.connect(self._on_engine_started)
        self._signals.devices.connect(self._on_devices_found)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._on_tick)
        self._build_ui()
        self._sync_license_ui()
        self._refresh_project_list()
        self._sync_mode_widgets()
        self._sync_camera_choice()
        self._refresh_source_label()
        self._set_state("idle", "选好设备和素材后，点击开始预览。摄像头尚未开启。")
        if self.preferences.last_error:
            self._notice("上次设置无法读取，已使用默认值。可以重新选择设备和素材。")
            self.log.record("preferences_load_error", error=self.preferences.last_error)
        elif self.license.last_error:
            self._notice(self.license.last_error)
        self.log.record("app_start", version=__version__)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        title_row = QHBoxLayout()
        title = QLabel("FaceSwap Studio")
        title.setStyleSheet("font-size:26px;font-weight:600;padding:8px 0;")
        title_row.addWidget(title)
        title_row.addStretch()
        self.license_label = QLabel()
        self.license_label.setStyleSheet(
            "background:#e8eef6;border-radius:6px;padding:6px 10px;color:#334e70;"
        )
        title_row.addWidget(self.license_label)
        self.btn_activation = QPushButton("激活 / 授权")
        self.btn_activation.clicked.connect(self._show_activation)
        title_row.addWidget(self.btn_activation)
        outer.addLayout(title_row)
        subtitle = QLabel("实时通话与直播  ·  先确认本机画面，再开始输出")
        subtitle.setStyleSheet("color:#657185;padding-bottom:8px;")
        outer.addWidget(subtitle)
        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        controls = QWidget()
        controls.setObjectName("workflowControls")
        left = QVBoxLayout(controls)
        left.setContentsMargins(0, 0, 12, 0)
        device_box = QGroupBox("1  选择摄像头")
        device_layout = QVBoxLayout(device_box)
        self.camera_combo = QComboBox()
        self.camera_combo.currentIndexChanged.connect(self._on_camera_changed)
        device_layout.addWidget(self.camera_combo)
        self.btn_scan = QPushButton("查找设备（不会开启摄像头）")
        self.btn_scan.clicked.connect(self._scan_devices)
        device_layout.addWidget(self.btn_scan)
        self.camera_hint = QLabel("首次使用请查找设备；开始预览后确认画面来自正确的摄像头。")
        self.camera_hint.setWordWrap(True)
        device_layout.addWidget(self.camera_hint)
        left.addWidget(device_box)
        source_box = QGroupBox("2  选择照片或专属模型")
        source_layout = QVBoxLayout(source_box)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("照片模式", "simple")
        self.mode_combo.addItem("专业人物模型", "pro")
        self.mode_combo.addItem("设备测试（不换脸）", "demo")
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(self.settings["work_mode"]))
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        source_layout.addWidget(self.mode_combo)
        self.btn_import = QPushButton("选择照片…")
        self.btn_import.clicked.connect(self._import_asset)
        self.btn_dfm = QPushButton("导入专业人物模型…")
        self.btn_dfm.clicked.connect(self._choose_dfm)
        source_layout.addWidget(self.btn_import)
        source_layout.addWidget(self.btn_dfm)
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        self.dfm_label = self.source_label
        source_layout.addWidget(self.source_label)
        self.mode_hint = QLabel()
        self.mode_hint.setWordWrap(True)
        source_layout.addWidget(self.mode_hint)
        self.consent_box = QCheckBox("我拥有这些素材，或已获得使用许可")
        self.consent_box.setChecked(self.settings["consent_acked"])
        self.consent_box.toggled.connect(self._on_consent_toggled)
        source_layout.addWidget(self.consent_box)
        left.addWidget(source_box)
        preview_box = QGroupBox("3  检查本机预览")
        preview_layout = QVBoxLayout(preview_box)
        actions = QHBoxLayout()
        self.btn_start = QPushButton("开始预览")
        self.btn_start.setObjectName("primaryButton")
        self.btn_start.clicked.connect(self._start_preview)
        self.btn_stop = QPushButton("停止预览")
        self.btn_stop.clicked.connect(self._stop_preview)
        actions.addWidget(self.btn_start)
        actions.addWidget(self.btn_stop)
        preview_layout.addLayout(actions)
        self.btn_settings = QPushButton("画面与引擎设置…")
        self.btn_settings.clicked.connect(self._open_settings)
        preview_layout.addWidget(self.btn_settings)
        left.addWidget(preview_box)
        output_box = QGroupBox("4  开始输出并检查通话软件")
        output_layout = QVBoxLayout(output_box)
        self.btn_output_start = QPushButton("开始输出")
        self.btn_output_start.setObjectName("primaryButton")
        self.btn_output_start.clicked.connect(self._start_output)
        self.btn_output_pause = QPushButton("暂停输出")
        self.btn_output_pause.clicked.connect(lambda: self._pause_output("已手动暂停输出"))
        output_actions = QHBoxLayout()
        output_actions.addWidget(self.btn_output_start)
        output_actions.addWidget(self.btn_output_pause)
        output_layout.addLayout(output_actions)
        self.output_info = QLabel("等待真实换脸预览。演示画面与原摄像头画面不会输出。")
        self.output_info.setWordWrap(True)
        output_layout.addWidget(self.output_info)
        self.btn_install_output = QPushButton("准备虚拟摄像头…")
        self.btn_install_output.clicked.connect(self._install_output_component)
        output_layout.addWidget(self.btn_install_output)
        self.btn_output_help = QPushButton("如何检查输出？")
        self.btn_output_help.clicked.connect(self._show_output_help)
        output_layout.addWidget(self.btn_output_help)
        left.addWidget(output_box)
        self.btn_projects = QPushButton("项目与参考帧（可选） ▸")
        self.btn_projects.setCheckable(True)
        left.addWidget(self.btn_projects)
        self.project_panel = QWidget()
        project_layout = QVBoxLayout(self.project_panel)
        self.project_list = QListWidget()
        self.project_list.setMaximumHeight(110)
        self.project_list.currentTextChanged.connect(self._on_project_selected)
        project_layout.addWidget(self.project_list)
        project_actions = QHBoxLayout()
        self.btn_new = QPushButton("新建")
        self.btn_new.clicked.connect(self._new_project)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self._refresh_project_list)
        project_actions.addWidget(self.btn_new)
        project_actions.addWidget(self.btn_refresh)
        project_layout.addLayout(project_actions)
        self.asset_list = QListWidget()
        self.asset_list.setMaximumHeight(80)
        project_layout.addWidget(self.asset_list)
        self.watermark_box = QCheckBox("保存参考帧时添加预览标记")
        self.watermark_box.setChecked(self.settings["watermark_enabled"])
        self.watermark_box.toggled.connect(self._on_watermark_toggled)
        project_layout.addWidget(self.watermark_box)
        self.btn_export = QPushButton("保存当前参考帧…")
        self.btn_export.clicked.connect(self._export_frame)
        project_layout.addWidget(self.btn_export)
        self.project_panel.setVisible(False)
        self.btn_projects.toggled.connect(self.project_panel.setVisible)
        left.addWidget(self.project_panel)
        left.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls)
        scroll.setMinimumWidth(330)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        split.addWidget(scroll)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.state_label = QLabel()
        self.state_label.setStyleSheet("font-size:17px;font-weight:600;padding:8px 0;")
        right_layout.addWidget(self.state_label)
        self.preview_label = QLabel("摄像头尚未开启\n\n开始预览后，这里会显示本机画面")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(480, 300)
        self.preview_label.setStyleSheet(
            "background:#151c28;color:#b8c6da;border-radius:10px;padding:12px;"
        )
        right_layout.addWidget(self.preview_label, 1)
        self.engine_info = QLabel()
        self.engine_info.setWordWrap(True)
        right_layout.addWidget(self.engine_info)
        self.notice_label = QLabel()
        self.notice_label.setWordWrap(True)
        self.notice_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right_layout.addWidget(self.notice_label)
        self.btn_logs = QPushButton("打开诊断日志文件夹")
        self.btn_logs.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log.path.parent)))
        )
        right_layout.addWidget(self.btn_logs)
        split.addWidget(right)
        split.setSizes([370, 790])
        self.setStatusBar(QStatusBar())

    def _save_preferences(self):
        try:
            self.preferences.save(self.settings)
        except OSError as exc:
            self._notice(f"设置暂时无法保存：{exc}。本次操作仍可继续。")
            self.log.record("preferences_save_error", error=str(exc))

    def _notice(self, text):
        self.notice_label.setText(text)

    def _set_state(self, state, message):
        self.session_state = state
        labels = {
            "idle": "准备开始",
            "starting": "正在准备引擎",
            "waiting": "等待换脸首帧",
            "previewing": "本机换脸预览已就绪",
            "demo": "演示画面 · 未换脸",
            "external": "外部模型窗口已启动 · 尚未验证出画",
            "error": "需要处理后重试",
        }
        self.state_label.setText(labels.get(state, state))
        self.statusBar().showMessage(message)
        self.engine_info.setText(message)
        self._update_buttons()

    def _update_buttons(self):
        self.btn_start.setEnabled(not self._previewing)
        self.btn_stop.setEnabled(self._previewing)
        ready = self._real_frame_ready()
        output_state = _value(self.output.status()) if self.output else "stopped"
        self.btn_output_start.setEnabled(
            ready
            and self.license.state.allows_output()
            and output_state not in ("running", "starting")
        )
        self.btn_output_start.setToolTip(
            "" if self.license.state.allows_output() else "激活产品密钥后可输出到视频通话或直播软件"
        )
        self.btn_output_pause.setEnabled(output_state in ("running", "starting"))
        self.btn_export.setEnabled(self._last_frame is not None and self._previewing)

    def _sync_mode_widgets(self):
        mode = self.settings["work_mode"]
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(mode))
        self.mode_combo.blockSignals(False)
        self.btn_import.setVisible(mode == "simple")
        self.btn_dfm.setVisible(mode == "pro")
        self.btn_dfm.setEnabled(mode == "pro" and self.license.state.allows_pro_dfm())
        self.mode_hint.setText(
            {
                "simple": "默认 720p，最高 1080p。需要兼容的 FaceFusion 环境与已获许可模型；缺少依赖时会提示具体原因。",
                "pro": "适合反复使用的固定人物。当前通过专业模型窗口运行，需要 Pro / Studio 授权。",
                "demo": "仅检查摄像头和界面，不进行换脸，不允许开始输出。",
            }[mode]
        )

    def _sync_license_ui(self):
        self.license_label.setText(self.license.status_text())
        can_remove = self.license.state.allows_watermark_removal()
        self.watermark_box.blockSignals(True)
        if not can_remove:
            self.watermark_box.setChecked(True)
        else:
            self.watermark_box.setChecked(bool(self.settings["watermark_enabled"]))
        self.watermark_box.setEnabled(can_remove)
        self.watermark_box.setToolTip(
            "" if can_remove else "体验模式和 Starter 授权会保留预览标记"
        )
        self._sync_mode_widgets()
        self._update_buttons()

    def _show_activation(self):
        dialog = ActivationDialog(self.license, self)
        dialog.exec()
        self._sync_license_ui()
        if self.license.state.is_valid():
            self._notice("授权已验证，可以使用已开通的功能。")

    def _on_mode_changed(self, _index=0):
        mode = self.mode_combo.currentData()
        if not mode:
            return
        self._stop_preview()
        self.settings.update(work_mode=mode, engine=MODE_ENGINES[mode])
        if mode == "simple":
            self.settings["width"] = min(self.settings["width"], 1920)
            self.settings["height"] = min(self.settings["height"], 1080)
        self._sync_mode_widgets()
        self._refresh_source_label()
        self._save_preferences()
        self.log.record("mode_change", mode=mode)
        self._set_state("idle", "模式已切换，请检查素材后开始预览。")

    def _sync_camera_choice(self):
        index = self.settings["camera_index"]
        found = self.camera_combo.findData(index)
        self.camera_combo.blockSignals(True)
        if found < 0:
            label = self.settings.get("camera_name") or f"摄像头 {index + 1}（请查找设备确认）"
            self.camera_combo.addItem(label, index)
            found = self.camera_combo.findData(index)
        self.camera_combo.setCurrentIndex(found)
        self.camera_combo.blockSignals(False)

    def _scan_devices(self):
        if self._scan_running:
            return
        self._scan_running = True
        self.btn_scan.setEnabled(False)
        self.camera_hint.setText("正在读取设备列表，不会开启摄像头…")
        signals = self._signals

        def scan():
            devices, error = [], ""
            try:
                from face_swap_studio.core.cameras import camera_names

                devices = [
                    (i, name)
                    for i, name in enumerate(camera_names())
                    if name != "FaceSwap Studio Camera"
                ]
            except Exception as exc:  # noqa: BLE001 — contain backend failures at the GUI boundary
                error = str(exc)
            try:
                signals.devices.emit(devices, error)
            except RuntimeError:
                pass

        threading.Thread(target=scan, daemon=True).start()

    def _on_devices_found(self, devices, error):
        if self._closed:
            return
        self._scan_running = False
        self.btn_scan.setEnabled(True)
        self._camera_scan_empty = not devices and not error
        if devices:
            self.camera_combo.blockSignals(True)
            self.camera_combo.clear()
            for index, name in devices:
                self.camera_combo.addItem(f"{name} · 设备 {index + 1}", index)
            selected = self.camera_combo.findData(self.settings["camera_index"])
            self.camera_combo.setCurrentIndex(max(0, selected))
            self.camera_combo.blockSignals(False)
            self._on_camera_changed()
            self.camera_hint.setText(
                "设备已找到，请在预览中确认画面。软件自身的输出设备不会列为输入。"
            )
        else:
            if not error:
                self.camera_combo.blockSignals(True)
                self.camera_combo.clear()
                self.camera_combo.addItem("未找到输入摄像头", None)
                self.camera_combo.blockSignals(False)
            self.camera_hint.setText(
                "未找到可枚举设备。请连接摄像头、检查系统权限，或在设置中指定设备号。"
            )
        if error:
            self.log.record("device_scan_error", error=error)

    def _on_camera_changed(self, _index=0):
        value = self.camera_combo.currentData()
        if value is None:
            return
        if value != self.settings["camera_index"]:
            self._stop_preview()
        self.settings["camera_index"] = int(value)
        self.settings["camera_name"] = self.camera_combo.currentText()
        self._save_preferences()

    def _refresh_source_label(self):
        paths = self._asset_paths()
        if self.settings["work_mode"] == "pro":
            path = self.settings.get("dfm_path", "")
            self.source_label.setText(Path(path).name if path else "尚未选择专属模型")
        elif self.settings["work_mode"] == "demo":
            self.source_label.setText("演示无需照片")
        else:
            self.source_label.setText(
                Path(paths[0]).name if paths else "尚未选择照片 · 无需创建项目"
            )

    def _asset_paths(self):
        if self.current:
            root = self.store.project_dir(self.current.name)
            return [
                str(root / item["path"])
                for item in self.current.assets
                if (root / item["path"]).is_file()
            ]
        return list(self.settings.get("source_face_paths", []))

    def _import_asset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择本人或已获许可的照片", "", "照片 (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if path:
            self._select_photo(path)

    def _select_photo(self, path):
        try:
            image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("照片无法读取，请换一张 JPG 或 PNG 图片。")
        except (OSError, ValueError, cv2.error) as exc:
            self._notice(str(exc))
            return False
        self._stop_preview()
        if self.current:
            self.current = self.store.add_asset(
                self.current, path, Path(path).stem, self.consent_box.isChecked()
            )
            self._reload_assets()
        else:
            self.settings["source_face_paths"] = [str(Path(path).resolve())]
        self._save_preferences()
        self._refresh_source_label()
        self._notice("照片已选择。请确认使用许可，再开始预览。")
        return True

    def _choose_dfm(self):
        if not self.license.state.allows_pro_dfm():
            self._notice("专属模型模式需要已激活的 Pro / Studio 授权。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择已获许可的专属模型", "", "专属模型 (*.dfm)"
        )
        if path:
            self._stop_preview()
            self.settings["dfm_path"] = path
            self._save_preferences()
            self._refresh_source_label()

    def _on_consent_toggled(self, checked):
        self.settings["consent_acked"] = bool(checked)
        if self.current:
            self.current.consent_checklist_acked = bool(checked)
            self.store.save(self.current)
        self._save_preferences()
        if not checked and self.settings["work_mode"] != "demo":
            self._stop_preview()

    def _on_watermark_toggled(self, checked):
        self.settings["watermark_enabled"] = bool(checked)
        if self.current:
            self.current.watermark_enabled = bool(checked)
            self.store.save(self.current)
        self._save_preferences()

    def _open_settings(self):
        dialog = SettingsDialog(
            self, **{key: self.settings[key] for key in DIALOG_KEYS if key in self.settings}
        )
        if dialog.exec():
            self._stop_preview()
            self.settings.update(dialog.values())
            self.settings["engine"] = MODE_ENGINES[self.settings["work_mode"]]
            self.settings["camera_name"] = ""
            self._sync_camera_choice()
            self._save_preferences()
            self._notice("设置已保存。再次开始预览后生效。")

    def _start_preview(self):
        if self._previewing:
            return
        mode = self.settings["work_mode"]
        if self._camera_scan_empty:
            self._notice("请先连接输入摄像头，再点击「查找设备」。虚拟输出摄像头不能作为本程序输入。")
            return
        if mode != "demo" and not self.consent_box.isChecked():
            self._notice("请先确认照片或模型的使用许可。")
            return
        if mode == "simple" and not self._asset_paths():
            self._notice("请先选择一张照片，无需创建项目。")
            return
        if mode == "pro" and not self.license.state.allows_pro_dfm():
            self._notice("专属模型模式需要已激活的 Pro / Studio 授权。")
            return
        if mode == "pro" and not self.settings.get("dfm_path"):
            self._notice("请先选择 .dfm 专属模型。")
            return
        self.settings["engine"] = MODE_ENGINES[mode]
        self._generation += 1
        generation = self._generation
        self._startup_cancel = cancel = threading.Event()
        self._previewing = True
        self._starting_job = True
        self._last_frame = self._last_real_frame = None
        self._last_frame_id = None
        self._started_at = self._clock()
        self._last_frame_at = self._started_at
        self._notice("")
        self.preview_label.clear()
        self.preview_label.setText("正在准备，请稍候…\n尚未开始输出")
        self._set_state("starting", "正在检查环境并启动引擎；成功出画前不会开始输出。")
        self._timer.start()
        show_watermark = (
            not self.license.state.allows_watermark_removal()
            or self.watermark_box.isChecked()
        )
        cfg = build_engine_config(
            self.settings,
            source_face_paths=self._asset_paths(),
            watermark_text="FaceSwap Studio · Preview" if show_watermark else None,
        )
        try:
            engine = self._factory(self.settings["engine"])
        except Exception as exc:  # noqa: BLE001 — backend factory must not close the app
            self._starting_job = False
            self._fail_preview(str(exc))
            return
        self.engine = engine
        signals = self._signals
        cleanup = self._cleanup_thread
        self.log.record("preview_start_requested", mode=mode, engine=self.settings["engine"])

        def start():
            error = None
            try:
                if cleanup:
                    cleanup.join()
                if not cancel.is_set():
                    engine.initialize(cfg)
                if not cancel.is_set():
                    engine.start()
            except Exception as exc:  # noqa: BLE001 — contain backend failures at the GUI boundary
                error = str(exc)
            if cancel.is_set():
                shutdown_engine(engine)
                return
            try:
                signals.started.emit(generation, engine, error)
            except RuntimeError:
                shutdown_engine(engine)

        threading.Thread(target=start, daemon=True).start()

    def _on_engine_started(self, generation, engine, error):
        if self._closed or generation != self._generation:
            threading.Thread(target=shutdown_engine, args=(engine,), daemon=True).start()
            return
        self._starting_job = False
        if error:
            self._fail_preview(error)
            return
        capabilities = engine.capabilities()
        if (
            getattr(capabilities, "preview_mode", "internal") == "external"
            or self.settings["work_mode"] == "pro"
        ):
            self.preview_label.setText(
                "请在 DeepFaceLive 外部窗口选择模型并检查画面\n\n本程序尚未接收其视频帧，不能在这里开始输出。"
            )
            self._set_state("external", "已发起外部窗口启动；进程存活不代表模型已加载或已换脸。")
        else:
            self._set_state("waiting", "引擎已启动，正在等待画面。真人换脸首帧通过后才会启用输出。")

    def _retire_engine(self):
        engine, self.engine = self.engine, None
        if engine is not None and not self._starting_job:
            self._cleanup_thread = threading.Thread(
                target=shutdown_engine, args=(engine,), daemon=True
            )
            self._cleanup_thread.start()

    def _stop_preview(self):
        self._generation += 1
        self._startup_cancel.set()
        self._timer.stop()
        self._previewing = False
        if self.output:
            self.output.stop()
        self._retire_engine()
        self._starting_job = False
        self._last_frame = self._last_real_frame = None
        self._last_frame_id = None
        self.preview_label.clear()
        self.preview_label.setText("预览已停止\n摄像头画面不会继续输出")
        self.output_info.setText("输出已停止。重新预览并确认后可再次开始。")
        self._set_state("idle", "预览与输出已停止。")
        self.log.record("preview_stop")

    def _fail_preview(self, message):
        self._stop_preview()
        self._set_state("error", "引擎未能继续预览。处理原因后可重试。")
        self._notice(
            f"{message}\n可到「画面与引擎设置」检查安装路径、模型和设备；诊断日志：{self.log.path}"
        )
        self.log.record("preview_error", error=message, engine=self.settings["engine"])

    def _is_real_frame(self, frame):
        if frame is None or self.engine is None:
            return False
        meta = frame.meta or {}
        return (
            not self.engine.capabilities().is_stub
            and meta.get("stub") is False
            and meta.get("face_swapped") is True
            and meta.get("safe_to_output") is True
        )

    def _real_frame_ready(self):
        return (
            self._previewing
            and self.session_state == "previewing"
            and self._last_real_frame is not None
            and self._clock() - self._last_frame_at < 1.0
        )

    def _on_tick(self):
        if not self._previewing or self.engine is None:
            return
        now = self._clock()
        timeout = float(self.settings["facefusion_startup_timeout"])
        if self._starting_job:
            if now - self._started_at > timeout:
                self._fail_preview("启动等待超时。请检查引擎环境与模型文件后重试。")
            return
        try:
            status = _value(self.engine.status())
            if status in ("error", "unavailable"):
                detail = getattr(self.engine, "last_error", lambda: "")() or "引擎已退出。"
                self._fail_preview(detail)
                return
            if status in ("ready", "stopped"):
                self._fail_preview("引擎进程已结束或摄像头已停止，请重新开始预览。")
                return
            if self.session_state == "external":
                return
            frame = self.engine.read_frame()
            if frame is not None:
                frame_id = (frame.meta or {}).get("frame_id")
                duplicate = frame_id is not None and frame_id == self._last_frame_id
                if not duplicate:
                    self._last_frame_id = frame_id
                    self._show_bgr(frame.image)
                    self._last_frame = frame
                    if self._is_real_frame(frame):
                        self._last_real_frame = frame
                        self._last_frame_at = now
                        first = self.session_state != "previewing"
                        self._set_state(
                            "previewing",
                            f"本机换脸预览 · {frame.fps:.1f} FPS；请检查嘴型、侧脸和遮挡。",
                        )
                        if first:
                            self.log.record("real_preview_ready")
                        if (
                            self.output
                            and _value(self.output.status()) == "running"
                            and not self.output.send(frame)
                        ):
                            self._pause_output(
                                self.output.last_error()
                                or "输出未接收画面，请检查虚拟摄像头后重试。"
                            )
                    elif self.engine.capabilities().is_stub:
                        self._set_state("demo", "演示画面已显示；未进行换脸，不能用于输出。")
                    else:
                        if self.session_state == "previewing":
                            self._started_at = now
                        self._last_real_frame = None
                        self._pause_output(
                            (frame.meta or {}).get("reason")
                            or "暂未检测到可用的换脸画面，输出已暂停。"
                        )
                        self._set_state("waiting", "请正对摄像头，等待可用的换脸画面。")
            if (
                self.session_state == "waiting"
                and self._last_real_frame is None
                and now - self._started_at > timeout
            ):
                self._fail_preview(
                    "在等待上限内没有收到真实换脸首帧。请检查摄像头、照片、光线和模型。"
                )
                return
            if self.session_state == "previewing" and now - self._last_frame_at >= 1.0:
                self._last_real_frame = None
                self._pause_output("换脸画面中断，输出已暂停。恢复预览后请手动重新开始输出。")
                self._set_state("waiting", "画面中断，等待引擎恢复；当前没有继续输出。")
                self._started_at = now
            self._sync_output_status()
            self._update_buttons()
        except Exception as exc:  # noqa: BLE001 — contain backend failures at the GUI boundary
            self._fail_preview(str(exc))

    def _show_bgr(self, bgr):
        if (
            not isinstance(bgr, np.ndarray)
            or bgr.dtype != np.uint8
            or bgr.ndim != 3
            or bgr.shape[2] != 3
        ):
            raise ValueError("引擎返回了无法显示的画面格式。")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        qimage = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
        self.preview_label.setPixmap(
            QPixmap.fromImage(qimage).scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _start_output(self):
        if not self.license.state.allows_output():
            self._notice("体验模式可检查带标记的本机预览；激活产品密钥后才能开始视频输出。")
            return
        if not self._real_frame_ready():
            self._notice("先取得真实换脸预览并确认画面，再开始输出。")
            return
        try:
            if self.output is None:
                if self._output_factory is None:
                    from face_swap_studio.outputs.virtual_camera import VirtualCameraOutput

                    self._output_factory = VirtualCameraOutput
                self.output = self._output_factory()
            frame = self._last_real_frame
            h, w = frame.image.shape[:2]
            self.output.start(w, h, 30)
            if not self.output.send(frame):
                self._pause_output(self.output.last_error() or "输出暂未准备好，请稍后重试。")
                return
            self.output_info.setText(
                "正在启动虚拟摄像头。请等待设备就绪后，在通话或直播软件中选择它。"
            )
            self.log.record("output_start_requested", width=w, height=h)
        except Exception as exc:  # noqa: BLE001 — contain backend failures at the GUI boundary
            self.output_info.setText(f"输出尚未启动：{exc}。请安装受支持的虚拟摄像头后重试。")
            self.log.record("output_error", error=str(exc))
        self._update_buttons()

    def _pause_output(self, reason):
        if self.output and _value(self.output.status()) in ("running", "starting"):
            self.output.pause(reason)
            self.log.record("output_paused", reason=reason)
        self.output_info.setText(reason)
        self._update_buttons()

    def _sync_output_status(self):
        if self.output is None:
            return
        status = _value(self.output.status())
        if status == "running" and getattr(self.output, "receiver_connected", True) is False:
            self.output_info.setText(
                f"发送端已就绪，等待 {self.output.device or 'FaceSwap Studio Camera'} 连接。请安装随软件提供的摄像头组件，并在通话软件中选择它。"
            )
        elif status == "running":
            self.output_info.setText(
                f"输出设备：{self.output.device}。请在目标软件中选择此设备，并用对方接收画面确认。"
            )
        elif status == "error":
            self.output_info.setText(
                f"输出失败：{self.output.last_error()}。检查虚拟摄像头安装与设备占用后，可重新开始输出。"
            )
        elif status == "paused":
            self.output_info.setText(
                self.output.last_error() or "输出已暂停。确认预览后手动重新开始。"
            )

    def _install_output_component(self):
        if sys.platform != "win32":
            self._notice("虚拟摄像头组件目前用于 Windows，请在 Windows 安装包中完成准备。")
            return
        if getattr(sys, "frozen", False):
            installer = Path(sys.executable).parent / "components" / "FaceSwapStudio-Camera-Setup.exe"
        else:
            installer = Path(__file__).resolve().parents[3] / "dist" / "artifacts" / "FaceSwapStudio-Camera-Setup.exe"
        if not installer.is_file():
            self._notice("未找到摄像头安装组件。请完整安装主程序，或运行下载包中的 FaceSwapStudio-Camera-Setup.exe。")
            return
        self._stop_preview()
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(installer))):
            self._notice("请完成弹出的组件安装，然后重新打开通话或直播软件。组件安装需要 Windows 管理员权限。")
        else:
            self._notice("未能打开安装组件，请从开始菜单运行「安装虚拟摄像头组件」。")

    def _show_output_help(self):
        QMessageBox.information(
            self,
            "输出检查",
            "1. 先确认本机真实换脸画面。\n2. 安装随软件提供的 FaceSwap Studio Camera 组件，点击「开始输出」。\n3. 在通话或直播软件中选择 FaceSwap Studio Camera。\n4. 请对方确认收到正确画面、声音和嘴型。\n\n软件中的输出就绪不等于目标平台兼容性已验证。此版本的专属模型仅外部启动，不能从本程序输出。",
        )

    def _refresh_project_list(self):
        name = self.current.name if self.current else ""
        self.project_list.blockSignals(True)
        self.project_list.clear()
        self.project_list.addItem("不使用项目")
        self.project_list.addItems(self.store.list_projects())
        matches = self.project_list.findItems(name or "不使用项目", Qt.MatchFlag.MatchExactly)
        if matches:
            self.project_list.setCurrentItem(matches[0])
        self.project_list.blockSignals(False)

    def _new_project(self):
        name, ok = QInputDialog.getText(self, "新建项目", "项目名称")
        if not ok or not name.strip():
            return
        try:
            project = self.store.create(name)
        except (FileExistsError, ValueError) as exc:
            self._notice(str(exc))
            return
        self._refresh_project_list()
        self.project_list.setCurrentItem(
            self.project_list.findItems(project.name, Qt.MatchFlag.MatchExactly)[0]
        )

    def _on_project_selected(self, name):
        self._stop_preview()
        self.current = None
        if name and name != "不使用项目":
            try:
                self.current = self.store.load(name)
            except Exception as exc:  # noqa: BLE001 — contain backend failures at the GUI boundary
                self._notice(f"项目无法打开：{exc}")
        self.consent_box.blockSignals(True)
        self.consent_box.setChecked(
            self.current.consent_checklist_acked if self.current else self.settings["consent_acked"]
        )
        self.consent_box.blockSignals(False)
        self.watermark_box.blockSignals(True)
        self.watermark_box.setChecked(
            self.current.watermark_enabled if self.current else self.settings["watermark_enabled"]
        )
        self.watermark_box.blockSignals(False)
        self._reload_assets()
        self._refresh_source_label()

    def _reload_assets(self):
        self.asset_list.clear()
        if self.current:
            self.asset_list.addItems([a.get("label", "照片") for a in self.current.assets])

    def _export_frame(self):
        if self._last_frame is None or not self._previewing:
            self._notice("请先取得可见的预览画面。")
            return
        folder = (
            self.store.project_dir(self.current.name) / "exports"
            if self.current
            else self.store.root.parent / "exports"
        )
        folder.mkdir(parents=True, exist_ok=True)
        default = (
            folder / f"preview_{datetime.now(UTC).astimezone().strftime('%Y%m%d_%H%M%S_%f')}.png"
        )
        path, _ = QFileDialog.getSaveFileName(self, "保存当前参考帧", str(default), "PNG (*.png)")
        if not path:
            return
        try:
            image = self._last_frame.image.copy()
            if self.watermark_box.isChecked():
                cv2.putText(
                    image,
                    "FaceSwap Studio - Preview",
                    (16, image.shape[0] - 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 230, 255),
                    1,
                    cv2.LINE_AA,
                )
            ok, encoded = cv2.imencode(".png", image)
            if not ok:
                raise ValueError("图片编码失败")
            encoded.tofile(path)
            self._notice(f"参考帧已保存：{path}")
            self.log.record(
                "export_frame", path=path, real_swap=self._is_real_frame(self._last_frame)
            )
        except (OSError, ValueError, cv2.error) as exc:
            self._notice(f"参考帧未保存：{exc}")

    def closeEvent(self, event):
        self._closed = True
        self._stop_preview()
        self._save_preferences()
        self.log.record("app_exit")
        super().closeEvent(event)
