"""Launch the frozen GUI without a GPU, user Python or a console window."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


def smoke(executable: Path, report: Path, data_dir: Path | None = None) -> None:
    executable = executable.resolve(strict=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="fss-package-smoke-") as temporary:
        env = os.environ.copy()
        env.update(
            FSS_SMOKE="1",
            FSS_OFFSCREEN="1",
            QT_QPA_PLATFORM="offscreen",
            FSS_DATA_DIR=str(data_dir.resolve() if data_dir else Path(temporary) / "userdata"),
        )
        # The executable must find its own bundled Python modules.
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        result = {"executable": executable.name, "gpu_required": False}
        try:
            completed = subprocess.run(
                [str(executable), "--offscreen"],
                cwd=temporary,
                env=env,
                capture_output=True,
                timeout=45,
                check=False,
            )
            result["exit_code"] = completed.returncode
            result["stdout"] = completed.stdout.decode("utf-8", errors="replace")
            result["stderr"] = completed.stderr.decode("utf-8", errors="replace")
            result["passed"] = completed.returncode == 0
        except subprocess.TimeoutExpired:
            result.update(passed=False, error="Frozen application did not exit within 45 seconds")
        finally:
            log = Path(env["FSS_DATA_DIR"]) / "logs" / "startup.log"
            if log.is_file():
                result["startup_log"] = log.read_text(encoding="utf-8", errors="replace")
            result["duration_seconds"] = round(time.monotonic() - started, 3)
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if not result["passed"]:
            raise SystemExit(f"Packaged GUI smoke test failed: {report}")
        print(f"Packaged GUI smoke test passed in {result['duration_seconds']} seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, help="Keep smoke-test data here for uninstall checks")
    options = parser.parse_args()
    smoke(options.executable, options.report, options.data_dir)
