"""Beginner Windows bats must not exit /b inside parentheses.

Explorer runs `cmd /c script.bat`. `exit /b` inside a parenthesized block
closes that cmd session, so the window flashes shut before pause.
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
BEGINNER_BATS = (
    "setup-all-win.bat",
    "setup-win.bat",
    "setup-deeplivecam-cpu-win.bat",
    "start-win.bat",
    "setup-all-win-debug.bat",
)
EXIT_B = re.compile(r"(?i)(?<![A-Za-z0-9_])exit\s+/b\b")


def _code_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        stripped = raw.lstrip()
        if stripped.upper().startswith("REM ") or stripped.upper() == "REM":
            continue
        if stripped.startswith("::"):
            continue
        lines.append((lineno, raw.replace("^(", "").replace("^)", "")))
    return lines


def _after_label(text: str, label: str) -> str:
    lines = text.replace("\r\n", "\n").splitlines()
    prefix = f":{label}".lower()
    for index, line in enumerate(lines):
        if line.strip().lower() == prefix:
            return "\n".join(lines[index:])
    raise AssertionError(f"missing label :{label}")


def exit_b_inside_parentheses(text: str) -> list[str]:
    depth = 0
    hits: list[str] = []
    for lineno, line in _code_lines(text):
        i = 0
        while i < len(line):
            match = EXIT_B.match(line, i)
            if match and depth > 0:
                hits.append(f"{lineno}: {line.strip()}")
                i = match.end()
                continue
            ch = line[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            i += 1
    return hits


def test_scanner_catches_exit_inside_parentheses() -> None:
    sample = "if errorlevel 1 (\n  exit /b 1\n)\n"
    assert exit_b_inside_parentheses(sample)
    assert exit_b_inside_parentheses('if /I "%X%"=="1" exit /b 0\n') == []
    assert exit_b_inside_parentheses("echo 1^)\nexit /b 0\n") == []


def test_beginner_bats_never_exit_inside_parentheses() -> None:
    for name in BEGINNER_BATS:
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert exit_b_inside_parentheses(text) == [], name


def test_setup_scripts_pause_on_failure_and_success() -> None:
    setup_all = (SCRIPTS / "setup-all-win.bat").read_text(encoding="utf-8")
    assert "FSS_SETUP_NOPAUSE=1" in setup_all
    assert "pause" in _after_label(setup_all, "fail")
    assert "\npause\nexit /b 0\n" in setup_all.replace("\r\n", "\n")

    setup_win = (SCRIPTS / "setup-win.bat").read_text(encoding="utf-8")
    assert 'if /I "%FSS_SETUP_NOPAUSE%"=="1" exit /b 0' in setup_win
    assert 'if /I "%FSS_SETUP_NOPAUSE%"=="1" exit /b 1' in setup_win
    assert "pause" in _after_label(setup_win, "fail")

    cpu = (SCRIPTS / "setup-deeplivecam-cpu-win.bat").read_text(encoding="utf-8")
    assert "goto :nested_ok" in cpu
    assert 'if /I "%FSS_DLC_NOPAUSE%"=="1" exit /b 1' in cpu
    assert "pause" in _after_label(cpu, "fail")
    assert "call :maybe_pause" not in cpu


def test_debug_bat_calls_setup_all_and_always_pauses() -> None:
    text = (SCRIPTS / "setup-all-win-debug.bat").read_text(encoding="utf-8")
    assert 'call "%~dp0setup-all-win.bat"' in text
    assert "pause" in text


def test_start_win_pauses_only_when_launch_fails() -> None:
    text = (SCRIPTS / "start-win.bat").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "pythonw.exe" in text
    assert 'start ""' in text
    assert "uv run" not in text
    assert "import face_swap_studio.ui.main_window" in text
    success = text.split('start ""', 1)[1].split("exit /b 0", 1)[0]
    assert "pause" not in success
    assert "pause" in _after_label(text, "fail")


def test_shortcut_script_prints_error_and_exits_nonzero() -> None:
    text = (SCRIPTS / "create-desktop-shortcut.ps1").read_text(encoding="utf-8")
    assert "[错误]" in text
    assert "exit 1" in text
    assert "cmd.exe" not in text
