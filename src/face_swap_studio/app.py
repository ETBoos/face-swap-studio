"""Application entry — FaceSwap Studio."""

from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    # Offscreen smoke support (CI / Linux box without display)
    if "--offscreen" in argv or os.environ.get("FSS_OFFSCREEN") == "1":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        argv = [a for a in argv if a != "--offscreen"]

    from PySide6.QtWidgets import QApplication

    from face_swap_studio.ui.main_window import MainWindow

    app = QApplication(argv)
    app.setApplicationName("FaceSwap Studio")
    app.setOrganizationName("FaceSwapStudio")

    win = MainWindow()
    win.show()

    if os.environ.get("FSS_SMOKE") == "1":
        # Quit shortly after showing — used for import/GUI smoke tests
        from PySide6.QtCore import QTimer

        QTimer.singleShot(400, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
