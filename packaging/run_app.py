"""Frozen entry point. Keep multiprocessing and startup logs working without a console."""

from __future__ import annotations

import multiprocessing
import os
import sys
import traceback
from pathlib import Path


def run() -> int:
    multiprocessing.freeze_support()
    data_root = Path(
        os.environ.get("FSS_DATA_DIR")
        or Path.home() / "FaceSwapStudio"
    )
    log_dir = data_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "startup.log"
    if sys.stdout is None or sys.stderr is None:
        stream = log_path.open("a", encoding="utf-8", buffering=1)
        sys.stdout = stream
        sys.stderr = stream
    try:
        from face_swap_studio.app import main

        return main()
    except Exception:  # noqa: BLE001 - final startup boundary logs unexpected failures
        traceback.print_exc()
        # A smoke failure must terminate instead of waiting on a hidden dialog.
        if sys.platform == "win32" and os.environ.get("FSS_SMOKE") != "1":
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                f"FaceSwap Studio 暂时无法启动。\n错误详情已保存到：\n{log_path}\n请将这份日志用于排查。",
                "FaceSwap Studio",
                0x10,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
