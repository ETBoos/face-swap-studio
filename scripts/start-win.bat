@echo off
REM FaceSwap Studio — Windows launcher
chcp 65001 >nul
setlocal EnableExtensions

set "ROOT=%~dp0.."
cd /d "%ROOT%"

echo 启动 FaceSwap Studio ...
echo 仅限授权影视用途 — AUTHORIZED FILM USE ONLY
echo.

where uv >nul 2>&1
if errorlevel 1 (
  if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m face_swap_studio
    goto :eof
  )
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
      py -3 -m face_swap_studio
      goto :eof
    )
  )
  where python >nul 2>&1
  if not errorlevel 1 (
    python -m face_swap_studio
    goto :eof
  )
  echo [错误] 未找到 python 或 py。请安装 Python 3.11 或更高版本，或将其加入 PATH。
  echo [Error] Neither python nor py was found. Install Python 3.11+ or fix PATH.
  echo 请先运行 scripts\setup-win.bat
  pause
  exit /b 1
)

uv run python -m face_swap_studio
if errorlevel 1 (
  echo [错误] 启动失败。请先运行 scripts\setup-win.bat
  pause
  exit /b 1
)
endlocal
