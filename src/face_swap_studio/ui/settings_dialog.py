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
DIALOG_KEYS = ("width", "height", "camera_index", "gpu_device", "engine")


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
            "说明：GPU 设备字符串将在接入 DeepFaceLive 后传给 CUDA 后端。\n"
            "推荐硬件：NVIDIA RTX 4080 / 4090（Windows + 最新 Studio 驱动）。\n"
            "当前占位引擎不使用 GPU。"
        )
        gpu_note.setWordWrap(True)
        form.addRow("", gpu_note)

        self.engine_combo = QComboBox()
        self.engine_combo.addItem("占位引擎 (Placeholder)", "placeholder")
        self.engine_combo.addItem("DeepFaceLive (未接入 / stub)", "deepfacelive")
        self.engine_combo.addItem("FaceFusion (简易)", "facefusion")
        idx = self.engine_combo.findData(engine)
        if idx >= 0:
            self.engine_combo.setCurrentIndex(idx)
        form.addRow("引擎", self.engine_combo)

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
        }
