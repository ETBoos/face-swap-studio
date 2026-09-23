"""Beginner-friendly license activation dialog."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class _ActivationSignals(QObject):
    done = Signal(bool, str)


class ActivationDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._busy = False
        self._signals = _ActivationSignals(self)
        self._signals.done.connect(self._on_done)
        self.setWindowTitle("产品激活")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setStyleSheet("font-size:16px;font-weight:600;")
        layout.addWidget(self.status)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)

        form = QFormLayout()
        self.device = QLineEdit(store.device_id)
        self.device.setReadOnly(True)
        self.device.setToolTip("客服解绑设备时需要此编号")
        form.addRow("本机设备码", self.device)
        self.key = QLineEdit()
        self.key.setPlaceholderText("FSS-XXXX-XXXX-XXXX-XXXX")
        self.key.setClearButtonEnabled(True)
        form.addRow("产品密钥", self.key)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.activate_button = QPushButton("联网激活")
        self.activate_button.setDefault(True)
        self.activate_button.clicked.connect(self._activate)
        self.refresh_button = QPushButton("刷新授权")
        self.refresh_button.clicked.connect(self._refresh)
        self.offline_button = QPushButton("导入离线授权…")
        self.offline_button.clicked.connect(self._offline)
        buttons.addWidget(self.activate_button)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.offline_button)
        layout.addLayout(buttons)

        footer = QHBoxLayout()
        self.deactivate_button = QPushButton("清除此电脑的授权")
        self.deactivate_button.clicked.connect(self._deactivate)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        footer.addWidget(self.deactivate_button)
        footer.addStretch()
        footer.addWidget(close_button)
        layout.addLayout(footer)
        self._sync()

    def _sync(self) -> None:
        self.status.setText(self.store.status_text())
        if self.store.state.is_valid():
            self.detail.setText(
                f"密钥尾号：{self.store.state.key_hint or '未知'}  ·  "
                f"设备额度：{self.store.state.seats}\n授权信息已通过数字签名验证。"
            )
        elif self.store.last_error:
            self.detail.setText(self.store.last_error)
        elif not self.store.activation_url:
            self.detail.setText("此安装版本未配置在线激活地址，可导入销售方提供的离线授权文件。")
        else:
            self.detail.setText("输入产品密钥后联网激活。产品密钥不会以明文保存在电脑中。")
        self.refresh_button.setEnabled(bool(self.store.state.signed_token))
        self.deactivate_button.setEnabled(bool(self.store.state.signed_token))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in (
            self.activate_button,
            self.refresh_button,
            self.offline_button,
            self.deactivate_button,
        ):
            button.setEnabled(not busy)
        if not busy:
            self._sync()

    def _run(self, operation, success: str) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self.detail.setText("正在验证授权，请稍候…")

        def worker():
            try:
                operation()
                self._signals.done.emit(True, success)
            except Exception as exc:  # noqa: BLE001 - show network/signature errors in the dialog
                self._signals.done.emit(False, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_done(self, ok: bool, message: str) -> None:
        self._set_busy(False)
        if ok:
            self.detail.setText(message)
            self.accept()
        else:
            self.detail.setText(message)

    def _activate(self) -> None:
        product_key = self.key.text().strip()
        if not product_key:
            self.detail.setText("请输入产品密钥。")
            return
        self._run(lambda: self.store.activate(product_key), "激活成功。")

    def _refresh(self) -> None:
        self._run(self.store.refresh, "授权已刷新。")

    def _offline(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择离线授权文件", "", "FaceSwap Studio 授权 (*.license *.txt);;所有文件 (*)"
        )
        if not path:
            return
        try:
            token = Path(path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            self.detail.setText(f"无法读取授权文件：{exc}")
            return
        self._run(lambda: self.store.import_offline_token(token), "离线授权已导入。")

    def _deactivate(self) -> None:
        answer = QMessageBox.question(
            self,
            "清除本机授权",
            "这只会清除本机凭证，不会释放服务器上的设备额度。确定继续吗？",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.store.deactivate_local()
            self._sync()
