"""Advanced configuration; work mode is selected only on the main screen."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

DIALOG_KEYS = (
    "work_mode",
    "width",
    "height",
    "camera_index",
    "gpu_device",
    "facefusion_root",
    "facefusion_python",
    "deepfacelive_root",
    "userdata_dir",
    "facefusion_model",
    "facefusion_execution_provider",
    "facefusion_startup_timeout",
)


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        work_mode="simple",
        width=1280,
        height=720,
        camera_index=0,
        gpu_device="cuda:0",
        facefusion_root="",
        facefusion_python="",
        deepfacelive_root="",
        userdata_dir="",
        facefusion_model="inswapper_128",
        facefusion_execution_provider="cuda",
        facefusion_startup_timeout=90,
        **_ignored,
    ):
        super().__init__(parent)
        self.setWindowTitle("画面与引擎设置")
        self.setMinimumWidth(590)
        layout = QVBoxLayout(self)
        note = QLabel(
            "模式请在主界面选择。安装目录为可选项；已配置环境时可留空。\n"
            "模型权重需自行准备并确认使用许可，本程序不会自动下载。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        layout.addLayout(form)
        self.width_spin = self._spin(320, 1920 if work_mode == "simple" else 3840, width)
        self.height_spin = self._spin(240, 1080 if work_mode == "simple" else 2160, height)
        resolution = QHBoxLayout()
        resolution.addWidget(self.width_spin)
        resolution.addWidget(QLabel("×"))
        resolution.addWidget(self.height_spin)
        form.addRow("预览尺寸", resolution)
        self.camera_spin = self._spin(0, 32, camera_index)
        form.addRow("设备号（名称不匹配时调整）", self.camera_spin)
        self.gpu_edit = QLineEdit(str(gpu_device))
        form.addRow("GPU 设备（高级）", self.gpu_edit)
        self.ff_root = self._path_field(form, "FaceFusion 安装目录", facefusion_root)
        self.ff_python = self._path_field(form, "FaceFusion Python", facefusion_python, file=True)
        self.dfl_root = self._path_field(form, "DeepFaceLive 安装目录", deepfacelive_root)
        self.userdata = self._path_field(form, "DeepFaceLive 用户目录", userdata_dir)
        self.model_edit = QLineEdit(facefusion_model)
        form.addRow("已准备的照片模型", self.model_edit)
        self.provider_combo = QComboBox()
        for label, value in (("NVIDIA GPU（CUDA）", "cuda"), ("CPU（速度有限）", "cpu")):
            self.provider_combo.addItem(label, value)
        index = self.provider_combo.findData(facefusion_execution_provider)
        self.provider_combo.setCurrentIndex(max(0, index))
        form.addRow("照片模型计算设备", self.provider_combo)
        self.timeout_spin = self._spin(10, 600, facefusion_startup_timeout)
        self.timeout_spin.setSuffix(" 秒")
        form.addRow("首帧等待上限", self.timeout_spin)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _spin(low, high, value):
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setValue(int(value))
        return spin

    def _path_field(self, form, label, value, file=False):
        line = QLineEdit(value)
        line.setPlaceholderText("可留空")
        row = QWidget()
        hbox = QHBoxLayout(row)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.addWidget(line)
        browse = QPushButton("选择…")
        hbox.addWidget(browse)

        def choose():
            if file:
                path, _ = QFileDialog.getOpenFileName(self, label, line.text())
            else:
                path = QFileDialog.getExistingDirectory(self, label, line.text())
            if path:
                line.setText(path)

        browse.clicked.connect(choose)
        form.addRow(label, row)
        return line

    def values(self):
        return {
            "width": self.width_spin.value(),
            "height": self.height_spin.value(),
            "camera_index": self.camera_spin.value(),
            "gpu_device": self.gpu_edit.text().strip() or "cuda:0",
            "facefusion_root": self.ff_root.text().strip(),
            "facefusion_python": self.ff_python.text().strip(),
            "deepfacelive_root": self.dfl_root.text().strip(),
            "userdata_dir": self.userdata.text().strip(),
            "facefusion_model": self.model_edit.text().strip() or "inswapper_128",
            "facefusion_execution_provider": self.provider_combo.currentData(),
            "facefusion_startup_timeout": self.timeout_spin.value(),
        }
