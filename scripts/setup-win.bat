@echo off
REM FaceSwap Studio — Windows setup (run from project root or this scripts folder)
chcp 65001 >nul
setlocal EnableExtensions

set "ROOT=%~dp0.."
cd /d "%ROOT%"

echo ============================================
echo  FaceSwap Studio 安装 (Windows)
echo  剧组换脸预览工作站 — 产品壳 + 引擎适配桩
echo ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 python。请先安装 Python 3.11+ 并勾选 Add to PATH。
  echo https://www.python.org/downloads/
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo [错误] 需要 Python 3.11 或更高版本。
  exit /b 1
)

where uv >nul 2>&1
if errorlevel 1 (
  echo [信息] 未检测到 uv，正在通过 pip 安装 uv...
  python -m pip install --upgrade uv
  if errorlevel 1 (
    echo [错误] uv 安装失败。也可手动: pip install uv
    exit /b 1
  )
)

echo [信息] 使用 uv 创建虚拟环境并安装依赖...
uv sync
if errorlevel 1 (
  echo [错误] uv sync 失败。
  exit /b 1
)

echo.
echo [完成] 安装成功。请运行 scripts\start-win.bat 启动。
echo [注意] 即用模式会启动本机 Deep-Live-Cam（需 DEEP_LIVE_CAM_ROOT）。未安装 DLC/DFL 时没有换脸画面。
echo [合规] 仅限授权影视用途。
echo.
pause
endlocal
