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
  python -m face_swap_studio
  goto :eof
)

uv run python -m face_swap_studio
if errorlevel 1 (
  echo [错误] 启动失败。请先运行 scripts\setup-win.bat
  pause
  exit /b 1
)
endlocal
