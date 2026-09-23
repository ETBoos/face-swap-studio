@echo off
REM FaceSwap Studio — one double-click for non-technical Windows users.
REM 1) Find Python. If %%USERPROFILE%%\Deep-Live-Cam is missing, install it
REM    with scripts\setup-deeplivecam-cpu-win.bat (CPU, prebuilt insightface).
REM 2) Write deeplivecam_root into %%USERPROFILE%%\FaceSwapStudio\settings.json.
REM 3) Put a Desktop shortcut named 打开换脸 that launches scripts\start-win.bat.
chcp 65001 >nul
setlocal EnableExtensions
title FaceSwap Studio 一键安装

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "ROOT=%CD%"
set "DLC_DIR=%USERPROFILE%\Deep-Live-Cam"

echo ============================================
echo  FaceSwap Studio 一键安装
echo  检测 Python 和 Deep-Live-Cam
echo  写好换脸路径，并创建桌面「打开换脸」
echo ============================================
echo.

set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"

if not defined PY (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
    if not defined PY set "PY=py"
  )
)

if not defined PY (
  echo [错误] 未找到 python 或 py。请安装 Python 3.11、3.12 或 3.13，并勾选 Add to PATH。
  echo https://www.python.org/downloads/
  pause
  exit /b 1
)

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo [错误] 需要 Python 3.11 或更高版本。
  pause
  exit /b 1
)

echo [1/4] 安装 FaceSwap Studio ...
set "FSS_SETUP_NOPAUSE=1"
call "%~dp0setup-win.bat"
if errorlevel 1 (
  echo [错误] FaceSwap Studio 安装失败。
  pause
  exit /b 1
)

echo.
echo [2/4] 检查 Deep-Live-Cam ...
echo 目标目录: %DLC_DIR%
set "DLC_READY=0"
if exist "%DLC_DIR%\run.py" if exist "%DLC_DIR%\modules\core.py" if exist "%DLC_DIR%\venv\Scripts\python.exe" set "DLC_READY=1"
set "FSS_PY=%PY%"
set "FSS_DLC_NOPAUSE=1"

if "%DLC_READY%"=="1" (
  echo [OK] 已找到 Deep-Live-Cam，跳过安装。
) else (
  echo [信息] 还没有可用的 Deep-Live-Cam，开始 CPU 一键安装 ...
  call "%~dp0setup-deeplivecam-cpu-win.bat"
  if errorlevel 1 (
    echo [错误] Deep-Live-Cam 安装失败。
    pause
    exit /b 1
  )
)

if not exist "%DLC_DIR%\run.py" (
  echo [错误] 安装后仍未找到 %DLC_DIR%\run.py
  pause
  exit /b 1
)
if not exist "%DLC_DIR%\modules\core.py" (
  echo [错误] 安装后仍未找到 %DLC_DIR%\modules\core.py
  pause
  exit /b 1
)

echo.
echo [3/4] 写入 Studio 设置（不用手填路径）...
set "PYTHONPATH=%ROOT%\src"
%PY% -m face_swap_studio.core.studio_settings --deeplivecam-root "%DLC_DIR%"
if errorlevel 1 (
  echo [错误] 写入设置失败。
  pause
  exit /b 1
)

echo.
echo [4/4] 创建桌面快捷方式「打开换脸」...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create-desktop-shortcut.ps1" -WorkingDirectory "%ROOT%"
if errorlevel 1 (
  echo [错误] 创建桌面快捷方式失败。
  pause
  exit /b 1
)

echo.
echo === 完成 ===
echo Deep-Live-Cam:
echo   %DLC_DIR%
echo 设置文件:
echo   %USERPROFILE%\FaceSwapStudio\settings.json
echo.
echo 请双击桌面上的「打开换脸」。
echo 打开后点「设置」，Deep-Live-Cam 目录应已经填好。
echo 本脚本只完成安装和配置，不验证摄像头换脸。
echo.
pause
endlocal
