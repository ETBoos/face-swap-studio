"""Settings dialog — resolution, GPU device note, engine selection."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

# Keys the dialog accepts; callers may pass a larger settings dict.
DIALOG_KEYS = (
    "width",
    "height",
    "camera_index",
    "gpu_device",
    "engine",
    "deeplivecam_root",
    "dlc_session",
    "execution_provider",
    "preview_target",
)


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        width: int = 1280,
        height: int = 720,
        camera_index: int = 0,
        gpu_device: str = "cuda:0",
        engine: str = "placeholder",
        deeplivecam_root: str = "",
        dlc_session: str = "preview",
        execution_provider: str = "",
        preview_target: str = "",
        **_ignored,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(420)

        form = QFormLayout()

        self.width_spin = QSpinBox()
        self.width_spin.setRange(320, 3840)
        self.width_spin.setValue(int(width))
        form.addRow("预览宽度", self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(240, 2160)
        self.height_spin.setValue(int(height))
        form.addRow("预览高度", self.height_spin)

        self.camera_spin = QSpinBox()
        self.camera_spin.setRange(0, 16)
        self.camera_spin.setValue(int(camera_index))
        form.addRow("摄像头索引", self.camera_spin)

        self.gpu_edit = QLineEdit(str(gpu_device))
        form.addRow("GPU 设备", self.gpu_edit)

        gpu_note = QLabel(
            "说明：即用模式把 GPU 设备映射成 Deep-Live-Cam 的 --execution-provider"
            "（cuda:0 → cuda）。专模仍把该字符串交给 DeepFaceLive。\n"
            "推荐硬件：NVIDIA RTX 4080 / 4090（Windows + 最新 Studio 驱动）。\n"
            "占位引擎不使用 GPU，也不做换脸。"
        )
        gpu_note.setWordWrap(True)
        form.addRow("", gpu_note)

        self.engine_combo = QComboBox()
        self.engine_combo.addItem("占位引擎 (调试，无换脸)", "placeholder")
        self.engine_combo.addItem("即用 Deep-Live-Cam", "deeplivecam")
        self.engine_combo.addItem("专模 DeepFaceLive", "deepfacelive")
        idx = self.engine_combo.findData(engine)
        if idx >= 0:
            self.engine_combo.setCurrentIndex(idx)
        form.addRow("引擎", self.engine_combo)

        self.dlc_root_edit = QLineEdit(str(deeplivecam_root))
        self.dlc_root_edit.setPlaceholderText(r"C:\Deep-Live-Cam 或留空用 DEEP_LIVE_CAM_ROOT")
        form.addRow("Deep-Live-Cam 目录", self.dlc_root_edit)

        self.session_combo = QComboBox()
        self.session_combo.addItem("首帧进预览窗", "preview")
        self.session_combo.addItem("DLC 实时窗口", "live")
        session_idx = self.session_combo.findData(dlc_session or "preview")
        if session_idx >= 0:
            self.session_combo.setCurrentIndex(session_idx)
        form.addRow("即用输出", self.session_combo)

        self.provider_edit = QLineEdit(str(execution_provider))
        self.provider_edit.setPlaceholderText("留空则按 GPU 设备推导，NVIDIA 默认 cuda")
        form.addRow("DLC execution-provider", self.provider_edit)

        self.preview_target_edit = QLineEdit(str(preview_target))
        self.preview_target_edit.setPlaceholderText("含人脸的目标静帧；留空则抓一张摄像头画面")
        form.addRow("首帧目标静帧", self.preview_target_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "width": self.width_spin.value(),
            "height": self.height_spin.value(),
            "camera_index": self.camera_spin.value(),
            "gpu_device": self.gpu_edit.text().strip() or "cuda:0",
            "engine": self.engine_combo.currentData(),
            "deeplivecam_root": self.dlc_root_edit.text().strip(),
            "dlc_session": self.session_combo.currentData(),
            "execution_provider": self.provider_edit.text().strip(),
            "preview_target": self.preview_target_edit.text().strip(),
        }
