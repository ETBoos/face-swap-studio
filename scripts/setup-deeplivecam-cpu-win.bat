@echo off
chcp 65001 >nul
setlocal EnableExtensions
title Deep-Live-Cam CPU 一键安装（免训即用）

REM 默认装到用户目录；可改这一行
set "DLC_DIR=%USERPROFILE%\Deep-Live-Cam"
set "MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple"

echo.
echo === Deep-Live-Cam 一键安装（CPU）===
echo 目标目录: %DLC_DIR%
echo.

where py >nul 2>&1
if errorlevel 1 (
  where python >nul 2>&1
  if errorlevel 1 (
    echo [错误] 未找到 py / python。请先安装 Python 3.11+ 并勾选 Add to PATH。
    pause
    exit /b 1
  )
  set "PY=python"
) else (
  set "PY=py -3"
)

where git >nul 2>&1
if errorlevel 1 (
  echo [提示] 未找到 git，将尝试用 PowerShell 下载 ZIP。
  set "USE_ZIP=1"
) else (
  set "USE_ZIP=0"
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [警告] PATH 里没有 ffmpeg。稍后请安装: winget install ffmpeg
  echo        或 https://www.gyan.dev/ffmpeg/builds/
) else (
  echo [OK] 已检测到 ffmpeg
)

if exist "%DLC_DIR%\run.py" (
  echo [OK] 已存在 Deep-Live-Cam，跳过下载。
  goto :venv
)

if "%USE_ZIP%"=="0" (
  echo [1/4] git clone ...
  git clone --depth 1 https://github.com/hacksider/Deep-Live-Cam.git "%DLC_DIR%"
  if errorlevel 1 (
    echo [错误] git clone 失败，改试 ZIP...
    set "USE_ZIP=1"
  )
)

if "%USE_ZIP%"=="1" (
  echo [1/4] 下载 ZIP...
  set "ZIP=%TEMP%\Deep-Live-Cam.zip"
  powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/hacksider/Deep-Live-Cam/archive/refs/heads/main.zip' -OutFile $env:ZIP"
  if errorlevel 1 (
    echo [错误] 下载失败，请手动从 GitHub 下 ZIP 解压到 %DLC_DIR%
    pause
    exit /b 1
  )
  powershell -NoProfile -Command "Expand-Archive -Force $env:ZIP (Join-Path $env:TEMP 'dlc-extract')"
  if exist "%TEMP%\dlc-extract\Deep-Live-Cam-main" (
    mkdir "%DLC_DIR%" 2>nul
    xcopy /E /I /Y "%TEMP%\dlc-extract\Deep-Live-Cam-main\*" "%DLC_DIR%\"
  )
)

if not exist "%DLC_DIR%\run.py" (
  echo [错误] 未找到 %DLC_DIR%\run.py
  pause
  exit /b 1
)

:venv
cd /d "%DLC_DIR%"
echo [2/4] 创建 venv ...
if not exist "venv\Scripts\python.exe" (
  %PY% -m venv venv
  if errorlevel 1 (
    echo [错误] 创建 venv 失败
    pause
    exit /b 1
  )
)

call venv\Scripts\activate.bat
echo [3/4] pip install -r requirements.txt （清华源）...
python -m pip install -U pip
python -m pip install -r requirements.txt -i %MIRROR%
if errorlevel 1 (
  echo [错误] pip 安装失败，可重跑本脚本或把报错发群。
  pause
  exit /b 1
)

echo [4/4] 下载模型到 models\ ...
if not exist "models" mkdir models
powershell -NoProfile -Command ^
  "$m='models';" ^
  "$files=@(" ^
  " @{n='inswapper_128_fp16.onnx';u='https://huggingface.co/hacksider/deep-live-cam/resolve/main/inswapper_128_fp16.onnx'}," ^
  " @{n='gfpgan-1024.onnx';u='https://huggingface.co/hacksider/deep-live-cam/resolve/main/gfpgan-1024.onnx'}" ^
  ");" ^
  "foreach($f in $files){ $p=Join-Path $m $f.n; if(-not (Test-Path $p)){ Write-Host ('下载 '+$f.n); Invoke-WebRequest -Uri $f.u -OutFile $p } else { Write-Host ('已有 '+$f.n) } }"

echo.
echo === 完成 ===
echo Deep-Live-Cam 目录:
echo   %DLC_DIR%
echo.
echo 下一步:
echo 1^) 若没有 ffmpeg: winget install ffmpeg ，然后新开终端
echo 2^) 可先试跑:   cd /d "%DLC_DIR%" ^&^& venv\Scripts\activate ^&^& python run.py
echo 3^) 打开 FaceSwap Studio → 设置 → Deep-Live-Cam 目录 填上面路径
echo 4^) 本机无独显，换脸会很慢，先验证能开窗/出首帧即可
echo.
pause
