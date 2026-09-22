"""Main window — Chinese GUI skeleton for film-crew face-swap preview."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from face_swap_studio import __version__
from face_swap_studio.core.consent import BANNER_ZH, CONSENT_CHECKLIST_ZH
from face_swap_studio.core.project import ProjectMeta, ProjectStore
from face_swap_studio.core.usage_log import UsageLog
from face_swap_studio.engines.base import EngineStatus
from face_swap_studio.engines.config_builder import build_engine_config
from face_swap_studio.engines.deepfacelive_stub import create_engine
from face_swap_studio.engines.lifecycle import replace_engine, shutdown_engine
from face_swap_studio.engines.modes import MODE_ENGINE_IDS, MODE_LABELS_ZH, WorkMode
from face_swap_studio.licensing.plans import PlanTier
from face_swap_studio.licensing.store import LicenseStore
from face_swap_studio.ui.settings_dialog import DIALOG_KEYS, SettingsDialog


def _default_projects_root() -> Path:
    return Path.home() / "FaceSwapStudio" / "projects"


class MainWindow(QMainWindow):
    def __init__(self, projects_root: Optional[Path] = None) -> None:
        super().__init__()
        self.setWindowTitle(f"FaceSwap Studio · 剧组换脸预览工作站  v{__version__}")
        self.resize(1200, 780)

        self.store = ProjectStore(projects_root or _default_projects_root())
        self.log = UsageLog(self.store.root.parent / "logs" / "usage.jsonl")
        self.license = LicenseStore(self.store.root.parent / "license.json")
        gate_issues = self.license.enforce_startup_gate()
        if gate_issues:
            self.log.record("license_gate", issues=gate_issues)
        self.current: Optional[ProjectMeta] = None
        self.engine = create_engine("placeholder")
        self.settings = {
            "width": 1280,
            "height": 720,
            "camera_index": 0,
            "gpu_device": "cuda:0",
            "engine": "placeholder",
            "work_mode": WorkMode.SIMPLE.value,
            "dfm_path": "",
            "facefusion_root": "",
            "deepfacelive_root": "",
            "userdata_dir": "",
            "deeplivecam_root": "",
            "deeplivecam_python": "",
            "dlc_session": "preview",
            "execution_provider": "",
            "preview_target": "",
            "instant_source_face": "",
        }
        self._previewing = False

        self._build_ui()
        self._refresh_project_list()
        self.log.record("app_start", version=__version__)

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 FPS tick
        self._timer.timeout.connect(self._on_tick)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # Compliance banner
        banner = QLabel(BANNER_ZH)
        banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner.setStyleSheet(
            "background:#8B0000;color:#fff;font-size:16px;font-weight:bold;"
            "padding:10px;border-radius:4px;"
        )
        root.addWidget(banner)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("工作模式"))
        from PySide6.QtWidgets import QComboBox

        self.mode_combo = QComboBox()
        for mode, label in MODE_LABELS_ZH.items():
            self.mode_combo.addItem(label, mode.value)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo, stretch=1)
        self.btn_dfm = QPushButton("选择 .dfm…")
        self.btn_dfm.clicked.connect(self._choose_dfm)
        self.btn_dfm.setEnabled(False)
        mode_row.addWidget(self.btn_dfm)
        self.dfm_label = QLabel("未选择 .dfm")
        self.dfm_label.setStyleSheet("color:#666;")
        mode_row.addWidget(self.dfm_label, stretch=1)
        self.btn_face = QPushButton("选择脸图…")
        self.btn_face.clicked.connect(self._choose_source_face)
        mode_row.addWidget(self.btn_face)
        self.face_label = QLabel("未选择源脸")
        self.face_label.setStyleSheet("color:#666;")
        mode_row.addWidget(self.face_label, stretch=1)
        mode_row.addWidget(QLabel("即用输出"))
        self.session_combo = QComboBox()
        self.session_combo.addItem("首帧进预览窗", "preview")
        self.session_combo.addItem("DLC 实时窗口", "live")
        self.session_combo.currentIndexChanged.connect(self._on_session_changed)
        mode_row.addWidget(self.session_combo)
        root.addLayout(mode_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, stretch=1)

        # Left: projects + assets
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.addWidget(QLabel("项目管理"))
        self.project_list = QListWidget()
        self.project_list.currentTextChanged.connect(self._on_project_selected)
        left_l.addWidget(self.project_list)

        btn_row = QHBoxLayout()
        self.btn_new = QPushButton("新建项目")
        self.btn_new.clicked.connect(self._new_project)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self._refresh_project_list)
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_refresh)
        left_l.addLayout(btn_row)

        left_l.addWidget(QLabel("授权素材"))
        self.asset_list = QListWidget()
        left_l.addWidget(self.asset_list)

        self.btn_import = QPushButton("导入授权素材…")
        self.btn_import.clicked.connect(self._import_asset)
        left_l.addWidget(self.btn_import)

        self.consent_box = QCheckBox("我已确认授权清单（见下方）")
        self.consent_box.stateChanged.connect(self._on_consent_toggled)
        left_l.addWidget(self.consent_box)

        checklist = QLabel("\n".join(f"• {c}" for c in CONSENT_CHECKLIST_ZH))
        checklist.setWordWrap(True)
        checklist.setStyleSheet("color:#444;font-size:11px;")
        left_l.addWidget(checklist)

        self.watermark_box = QCheckBox("导出/预览添加水印")
        self.watermark_box.setChecked(True)
        self.watermark_box.stateChanged.connect(self._on_watermark_toggled)
        left_l.addWidget(self.watermark_box)

        splitter.addWidget(left)

        # Right: preview + actions
        right = QWidget()
        right_l = QVBoxLayout(right)
        self.preview_caption = QLabel("预览")
        right_l.addWidget(self.preview_caption)
        self.preview_label = QLabel("尚未开始预览")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(640, 360)
        self.preview_label.setStyleSheet(
            "background:#1a1a1e;color:#aaa;border:1px solid #333;border-radius:4px;"
        )
        self.preview_label.setScaledContents(False)
        right_l.addWidget(self.preview_label, stretch=1)

        actions = QHBoxLayout()
        self.btn_start = QPushButton("开始预览")
        self.btn_start.clicked.connect(self._start_preview)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.clicked.connect(self._stop_preview)
        self.btn_stop.setEnabled(False)
        self.btn_export = QPushButton("导出参考帧")
        self.btn_export.clicked.connect(self._export_frame)
        self.btn_settings = QPushButton("设置…")
        self.btn_settings.clicked.connect(self._open_settings)
        actions.addWidget(self.btn_start)
        actions.addWidget(self.btn_stop)
        actions.addWidget(self.btn_export)
        actions.addWidget(self.btn_settings)
        right_l.addLayout(actions)

        self.engine_info = QLabel("引擎: Placeholder（stub）")
        right_l.addWidget(self.engine_info)

        splitter.addWidget(right)
        splitter.setSizes([360, 840])

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪 — 仅限授权影视用途")
        self._on_mode_changed()

    # --- projects ---

    def _refresh_project_list(self) -> None:
        self.project_list.clear()
        for name in self.store.list_projects():
            self.project_list.addItem(name)

    def _new_project(self) -> None:
        name, ok = QInputDialog.getText(self, "新建项目", "项目名称:")
        if not ok or not name.strip():
            return
        try:
            meta = self.store.create(name.strip())
        except (FileExistsError, ValueError) as e:
            QMessageBox.warning(self, "无法创建", str(e))
            return
        self.log.record("project_create", name=meta.name)
        self._refresh_project_list()
        items = self.project_list.findItems(meta.name, Qt.MatchFlag.MatchExactly)
        if items:
            self.project_list.setCurrentItem(items[0])

    def _on_project_selected(self, name: str) -> None:
        if self._previewing:
            self._stop_preview()
        shutdown_engine(self.engine)
        self.engine = create_engine(self.settings.get("engine", "placeholder"))
        if not name:
            self.current = None
            self.asset_list.clear()
            return
        try:
            self.current = self.store.load(name)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))
            return
        self.consent_box.blockSignals(True)
        self.consent_box.setChecked(self.current.consent_checklist_acked)
        self.consent_box.blockSignals(False)
        self.watermark_box.blockSignals(True)
        self.watermark_box.setChecked(self.current.watermark_enabled)
        self.watermark_box.blockSignals(False)
        self._reload_assets()
        self.statusBar().showMessage(f"已打开项目: {name}")

    def _reload_assets(self) -> None:
        self.asset_list.clear()
        if not self.current:
            return
        for a in self.current.assets:
            flag = "✓授权" if a.get("consent_confirmed") else "⚠未勾选"
            self.asset_list.addItem(f"[{flag}] {a.get('label', '')} — {a.get('path', '')}")

    def _import_asset(self) -> None:
        if not self.current:
            QMessageBox.information(self, "提示", "请先新建或选择项目")
            return
        if not self.current.consent_checklist_acked:
            QMessageBox.warning(
                self,
                "授权未确认",
                "导入素材前请勾选「我已确认授权清单」。",
            )
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择授权脸部素材",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All (*.*)",
        )
        if not path:
            return
        label, ok = QInputDialog.getText(self, "素材标签", "显示名称:", text=Path(path).stem)
        if not ok:
            return
        self.current = self.store.add_asset(
            self.current,
            path,
            label=label or Path(path).stem,
            consent_confirmed=True,
        )
        self.log.record("asset_import", project=self.current.name, path=path)
        self._reload_assets()

    def _on_consent_toggled(self, state: int) -> None:
        if not self.current:
            return
        self.current.consent_checklist_acked = state == Qt.CheckState.Checked.value or bool(state)
        # Qt6: state is int enum value
        self.current.consent_checklist_acked = self.consent_box.isChecked()
        self.store.save(self.current)
        self.log.record(
            "consent_ack",
            project=self.current.name,
            acked=self.current.consent_checklist_acked,
        )

    def _on_watermark_toggled(self) -> None:
        if not self.current:
            return
        self.current.watermark_enabled = self.watermark_box.isChecked()
        self.store.save(self.current)

    # --- preview ---

    def _open_settings(self) -> None:
        # Only pass dialog-known keys — full settings dict used to TypeError.
        dlg_kwargs = {k: self.settings[k] for k in DIALOG_KEYS if k in self.settings}
        dlg = SettingsDialog(self, **dlg_kwargs)
        if dlg.exec():
            vals = dlg.values()
            self.settings.update(vals)
            self._sync_session_combo()
            self._sync_dfm_label()
            engine = vals.get("engine")
            if engine == "deeplivecam":
                self._select_mode(WorkMode.SIMPLE)
            elif engine == "deepfacelive":
                self._select_mode(WorkMode.PRO)
            else:
                if self._previewing:
                    self._stop_preview()
                self.settings["engine"] = "placeholder"
                self.engine = replace_engine(self.engine, "placeholder", factory=create_engine)
                self.preview_label.clear()
                self.engine_info.setText("引擎: placeholder（调试占位，无换脸）")
            self._refresh_face_label()

    def _start_preview(self) -> None:
        if self._previewing:
            return
        if self.current and not self.current.consent_checklist_acked:
            reply = QMessageBox.question(
                self,
                "授权确认",
                "尚未勾选授权清单。仍要开始占位预览吗？\n（正式换脸接入后将强制要求授权）",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        engine_name = self._resolve_engine_name()
        self.settings["engine"] = engine_name
        if engine_name == "deepfacelive":
            if not self._pro_license_ok(notify=True):
                return
            if not self._ensure_dfm_selected():
                return
        if engine_name == "deeplivecam" and not self._source_face_paths():
            self._choose_source_face()
        source_faces = self._source_face_paths()
        if engine_name == "deeplivecam" and not source_faces:
            QMessageBox.information(self, "需要源脸", "即用模式请先选择一张脸图。")
            return
        self.engine = replace_engine(self.engine, engine_name, factory=create_engine)

        wm = None
        if not self.current or self.current.watermark_enabled:
            wm = "FaceSwap Studio · 授权预览"
        cfg = build_engine_config(
            self.settings,
            source_face_paths=source_faces,
            watermark_text=wm,
        )
        try:
            self.engine.initialize(cfg)
            if self.current:
                self.engine.set_source_faces(self._asset_paths())
            self.engine.start()
        except Exception as e:
            hint = ""
            if engine_name == "deeplivecam":
                hint = (
                    "\n\n即用模式只负责启动本机 Deep-Live-Cam，不在本程序里实现换脸。"
                    "请确认安装目录（设置或 DEEP_LIVE_CAM_ROOT）。"
                    "见 docs/DEEPLIVECAM_INSTANT.md。"
                )
            elif engine_name == "deepfacelive":
                hint = "\n\n专模模式启动本机 DeepFaceLive。请确认 .dfm 与 deepfacelive_root。"
            QMessageBox.critical(self, "引擎启动失败", f"{e}{hint}")
            self.log.record("preview_error", error=str(e), engine=engine_name)
            return

        caps = self.engine.capabilities()
        self.engine_info.setText(
            f"引擎: {caps.name} v{caps.version} | stub={caps.is_stub} | {caps.notes}"
        )
        self._previewing = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._timer.start()
        self.log.record("preview_start", engine=engine_name, stub=caps.is_stub)
        note = getattr(self.engine, "status_note", lambda: "")()
        if caps.is_stub:
            self.statusBar().showMessage("预览中（占位/stub — 无真实换脸）")
        elif note:
            self.statusBar().showMessage(note)
        else:
            self.statusBar().showMessage(f"预览中 · {caps.name}")

    def _resolve_engine_name(self) -> str:
        selected = str(self.settings.get("engine") or "")
        if selected == "placeholder":
            return "placeholder"
        try:
            mode = WorkMode(self.settings.get("work_mode", WorkMode.SIMPLE.value))
        except ValueError:
            mode = WorkMode.SIMPLE
        return MODE_ENGINE_IDS[mode]

    def _source_face_paths(self) -> list[str]:
        paths: list[str] = []
        pinned = str(self.settings.get("instant_source_face") or "")
        if pinned and Path(pinned).is_file():
            paths.append(str(Path(pinned)))
        for item in self._asset_paths():
            if item not in paths:
                paths.append(item)
        return paths

    def _asset_paths(self) -> list[str]:
        if not self.current:
            return []
        root = self.store.project_dir(self.current.name)
        out: list[str] = []
        for a in self.current.assets:
            p = root / a["path"]
            if p.is_file():
                out.append(str(p))
        return out

    def _stop_preview(self) -> None:
        self._timer.stop()
        self._previewing = False
        try:
            self.engine.stop()
        except Exception:
            pass
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.statusBar().showMessage("已停止预览")
        self.log.record("preview_stop")

    def _on_tick(self) -> None:
        frame = self.engine.read_frame()
        status = self.engine.status()
        if status == EngineStatus.ERROR:
            err = getattr(self.engine, "last_error", lambda: None)()
            self._stop_preview()
            QMessageBox.critical(self, "引擎失败", err or "Deep-Live-Cam / 引擎失败")
            return
        if frame is None:
            note = getattr(self.engine, "status_note", lambda: "")()
            if note:
                self.statusBar().showMessage(note)
            return
        self._show_bgr(frame.image)
        kind = (frame.meta or {}).get("kind")
        if kind == "first_frame":
            self.statusBar().showMessage(
                "即用首帧已出画（Deep-Live-Cam 静帧）。"
                "这不是摄像头实时循环；实时请改「DLC 实时窗口」，并在 Win+NVIDIA 上点 Live。"
            )
        elif frame.meta.get("stub"):
            self.statusBar().showMessage(f"预览中 ~{frame.fps:.1f} FPS | stub 引擎无真实换脸")
        else:
            self.statusBar().showMessage(f"预览中 ~{frame.fps:.1f} FPS")

    def _show_bgr(self, bgr: np.ndarray) -> None:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
        pix = QPixmap.fromImage(qimg)
        self.preview_label.setPixmap(
            pix.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _export_frame(self) -> None:
        if not self.current:
            QMessageBox.information(self, "提示", "请先选择项目（参考帧将写入项目 exports/）")
            return
        frame = self.engine.read_frame()
        if frame is None:
            # try one synthetic grab if not running
            QMessageBox.information(self, "提示", "请先开始预览后再导出参考帧")
            return
        export_dir = self.store.project_dir(self.current.name) / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone

        name = f"ref_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.png"
        out = export_dir / name
        img = frame.image
        if self.current.watermark_enabled:
            cv2.putText(
                img,
                "FaceSwap Studio · 授权参考帧",
                (20, img.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
        cv2.imwrite(str(out), img)
        self.log.record("export_frame", project=self.current.name, path=str(out))
        QMessageBox.information(self, "已导出", f"参考帧已保存:\n{out}")


    def _on_mode_changed(self, _index: int = 0) -> None:
        mode_val = self.mode_combo.currentData()
        try:
            mode = WorkMode(mode_val)
        except ValueError:
            mode = WorkMode.SIMPLE
        # Stop the live session and drop the previous process before the new engine exists.
        self.settings["work_mode"] = mode.value
        self.settings["engine"] = MODE_ENGINE_IDS[mode]
        if self._previewing:
            self._stop_preview()
        self.engine = replace_engine(
            self.engine, self.settings["engine"], factory=create_engine
        )
        self.preview_label.clear()
        pro = mode == WorkMode.PRO
        pro_ok = pro and self._pro_license_ok(notify=False)
        self.btn_dfm.setEnabled(pro_ok)
        self.dfm_label.setVisible(pro)
        instant = mode == WorkMode.SIMPLE
        self.btn_face.setEnabled(instant)
        self.btn_face.setVisible(instant)
        self.face_label.setVisible(instant)
        self.session_combo.setEnabled(instant)
        if instant:
            self.preview_caption.setText("即用预览（Deep-Live-Cam）")
            self.preview_label.setText(
                "选择脸图后点「开始预览」。\n"
                "默认：Deep-Live-Cam 静帧首帧进入本窗口。\n"
                "「DLC 实时窗口」会打开上游 Live 界面（需 Windows + NVIDIA 摄像头验收）。"
            )
            caps_name = "deeplivecam"
        else:
            self.preview_caption.setText("专模预览（DeepFaceLive）")
            self.preview_label.setText(
                "选择 .dfm 后开始预览。\n"
                "画面在 DeepFaceLive 窗口，本壳不拉流。\n"
                "RUNNING 不等于首帧。"
            )
            caps_name = "deepfacelive"
        self.engine_info.setText(f"引擎: {caps_name}（开始预览后启动）")
        self._sync_dfm_label()
        self._refresh_face_label()
        self.statusBar().showMessage(
            f"{MODE_LABELS_ZH[mode]} | 授权:{self.license.state.tier.value}"
        )
        self.log.record("mode_change", mode=mode.value, tier=self.license.state.tier.value)
        if pro and not pro_ok:
            QMessageBox.information(self, "授权提示", self._pro_license_message())

    def _select_mode(self, mode: WorkMode) -> None:
        idx = self.mode_combo.findData(mode.value)
        if idx < 0:
            return
        if self.mode_combo.currentIndex() != idx:
            self.mode_combo.setCurrentIndex(idx)
        else:
            self._on_mode_changed()

    def _on_session_changed(self, _index: int = 0) -> None:
        data = self.session_combo.currentData()
        if data:
            self.settings["dlc_session"] = data

    def _sync_session_combo(self) -> None:
        session = self.settings.get("dlc_session") or "preview"
        idx = self.session_combo.findData(session)
        if idx >= 0 and idx != self.session_combo.currentIndex():
            self.session_combo.blockSignals(True)
            self.session_combo.setCurrentIndex(idx)
            self.session_combo.blockSignals(False)

    def _refresh_face_label(self) -> None:
        pinned = str(self.settings.get("instant_source_face") or "")
        if pinned and Path(pinned).is_file():
            self.face_label.setText(Path(pinned).name)
            return
        paths = self._asset_paths()
        if paths:
            self.face_label.setText(Path(paths[0]).name)
            return
        self.face_label.setText("未选择源脸")

    def _choose_source_face(self) -> None:
        if self.current and not self.current.consent_checklist_acked:
            QMessageBox.warning(
                self,
                "授权未确认",
                "选择即用脸图前请勾选「我已确认授权清单」。",
            )
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择即用源脸",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All (*.*)",
        )
        if not path:
            return
        self.settings["instant_source_face"] = path
        if self.current and self.current.consent_checklist_acked:
            self.current = self.store.add_asset(
                self.current,
                path,
                label=Path(path).stem,
                consent_confirmed=True,
            )
            self.log.record("asset_import", project=self.current.name, path=path, via="instant")
            self._reload_assets()
        self.log.record("instant_source_face", path=path)
        self._refresh_face_label()

    def _pro_license_ok(self, *, notify: bool) -> bool:
        if self.license.state.allows_pro_dfm():
            return True
        if notify:
            QMessageBox.information(self, "授权提示", self._pro_license_message())
        return False

    def _pro_license_message(self) -> str:
        return (
            "专模（DeepFaceLive · .dfm）需要 Pro/Studio 且 USDT 开授权后启用。\n"
            f"当前档位: {self.license.state.tier.value} active={self.license.state.active}"
        )

    def _sync_dfm_label(self) -> None:
        dfm = str(self.settings.get("dfm_path") or "")
        if not dfm:
            self.dfm_label.setText("未选择 .dfm")
            return
        name = Path(dfm).name
        if Path(dfm).is_file():
            self.dfm_label.setText(name)
        else:
            self.dfm_label.setText(f"{name}（文件不存在）")

    def _ensure_dfm_selected(self) -> bool:
        """专模 requires an existing .dfm. Returns False if the user does not pick one."""
        dfm = str(self.settings.get("dfm_path") or "")
        if dfm and Path(dfm).is_file():
            self._sync_dfm_label()
            return True
        self._choose_dfm()
        dfm = str(self.settings.get("dfm_path") or "")
        if dfm and Path(dfm).is_file():
            return True
        QMessageBox.information(
            self,
            "需要 .dfm",
            "专模模式使用本机 DeepFaceLive，请先选择已有的 .dfm 文件。",
        )
        return False

    def _choose_dfm(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 DeepFaceLive 模型 (.dfm)", "", "DFM (*.dfm);;所有文件 (*)"
        )
        if not path:
            return
        self.settings["dfm_path"] = path
        self._sync_dfm_label()
        self.log.record("dfm_selected", path=path)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        shutdown_engine(self.engine)
        self.log.record("app_exit")
        super().closeEvent(event)
