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

if defined FSS_PY (
  set "PY=%FSS_PY%"
  goto :py_ready
)

where py >nul 2>&1
if errorlevel 1 (
  where python >nul 2>&1
  if errorlevel 1 (
    echo [错误] 未找到 py / python。请先安装 Python 3.11+ 并勾选 Add to PATH。
    goto :fail
  )
  set "PY=python"
) else (
  set "PY=py -3"
)

:py_ready

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
  echo [1/5] git clone ...
  git clone --depth 1 https://github.com/hacksider/Deep-Live-Cam.git "%DLC_DIR%"
  if errorlevel 1 (
    echo [错误] git clone 失败，改试 ZIP...
    set "USE_ZIP=1"
  )
)

if "%USE_ZIP%"=="1" (
  echo [1/5] 下载 ZIP...
  set "ZIP=%TEMP%\Deep-Live-Cam.zip"
  powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/hacksider/Deep-Live-Cam/archive/refs/heads/main.zip' -OutFile $env:ZIP"
  if errorlevel 1 (
    echo [错误] 下载失败，请手动从 GitHub 下 ZIP 解压到 %DLC_DIR%
    goto :fail
  )
  powershell -NoProfile -Command "Expand-Archive -Force $env:ZIP (Join-Path $env:TEMP 'dlc-extract')"
  if exist "%TEMP%\dlc-extract\Deep-Live-Cam-main" (
    mkdir "%DLC_DIR%" 2>nul
    xcopy /E /I /Y "%TEMP%\dlc-extract\Deep-Live-Cam-main\*" "%DLC_DIR%\"
  )
)

if not exist "%DLC_DIR%\run.py" (
  echo [错误] 未找到 %DLC_DIR%\run.py
  goto :fail
)

:venv
cd /d "%DLC_DIR%"
echo [2/5] 创建 venv ...
if not exist "venv\Scripts\python.exe" (
  %PY% -m venv venv
  if errorlevel 1 (
    echo [错误] 创建 venv 失败
    goto :fail
  )
)

call venv\Scripts\activate.bat
echo [3/5] 升级 pip，并安装预编译 insightface（不从源码编译）...
python -m pip install -U pip
if errorlevel 1 (
  echo [错误] 升级 pip 失败
  goto :fail
)

set "PY_MINOR="
for /f %%v in ('python -c "import sys; print(sys.version_info.minor)"') do set "PY_MINOR=%%v"
if not defined PY_MINOR (
  echo [错误] 无法检测 venv 里的 Python 版本。已停止，不会从源码编译 insightface。
  goto :fail
)
echo 检测到 Python 3.%PY_MINOR%

set "IF_TAG="
if "%PY_MINOR%"=="11" set "IF_TAG=cp311-cp311"
if "%PY_MINOR%"=="12" set "IF_TAG=cp312-cp312"
if "%PY_MINOR%"=="13" set "IF_TAG=cp313-cp313"
if not defined IF_TAG (
  echo [错误] Python 3.%PY_MINOR% 没有对应的预编译 insightface 轮子（仅 3.11 / 3.12 / 3.13）。
  echo        请改用 Python 3.11 或 3.12，或安装 Visual C++ Build Tools，或使用 https://deeplivecam.net
  echo        本脚本不会从源码编译 insightface。
  goto :fail
)

set "IF_WHL=insightface-0.7.3-%IF_TAG%-win_amd64.whl"
set "IF_URL=https://github.com/Gourieff/Assets/raw/main/Insightface/%IF_WHL%"
set "IF_PATH=%TEMP%\%IF_WHL%"
echo 下载 %IF_WHL%
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri $env:IF_URL -OutFile $env:IF_PATH -UseBasicParsing -Headers @{ 'User-Agent' = 'FaceSwapStudio-setup' }; if ((Get-Item $env:IF_PATH).Length -lt 100000) { exit 1 } } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
  echo [错误] 预编译 insightface 下载失败（Python 3.%PY_MINOR%：%IF_WHL%）。
  echo        请安装 Visual C++ Build Tools，或使用 https://deeplivecam.net
  echo        本脚本不会从源码编译 insightface，已停止安装。
  goto :fail
)

python -m pip install "%IF_PATH%" -i %MIRROR%
if errorlevel 1 (
  echo [错误] 预编译 insightface 安装失败（Python 3.%PY_MINOR%）。
  echo        请安装 Visual C++ Build Tools，或使用 https://deeplivecam.net
  echo        本脚本不会从源码编译 insightface，已停止安装。
  goto :fail
)

echo [4/5] pip install -r requirements.txt （清华源）...
python -m pip install -r requirements.txt -i %MIRROR% --only-binary insightface
if errorlevel 1 (
  echo [错误] pip 安装失败，可重跑本脚本或把报错发群。
  echo        insightface 只使用上面的预编译轮；若仍失败，请安装 Visual C++ Build Tools，或使用 https://deeplivecam.net
  goto :fail
)

echo [5/5] 下载模型到 models\ ...
if not exist "models" mkdir models
powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop'; $m='models';" ^
  "$files=@(" ^
  " @{n='inswapper_128_fp16.onnx';u='https://huggingface.co/hacksider/deep-live-cam/resolve/main/inswapper_128_fp16.onnx'}," ^
  " @{n='gfpgan-1024.onnx';u='https://huggingface.co/hacksider/deep-live-cam/resolve/main/gfpgan-1024.onnx'}" ^
  ");" ^
  "foreach($f in $files){ $p=Join-Path $m $f.n; if(-not (Test-Path $p)){ Write-Host ('下载 '+$f.n); Invoke-WebRequest -Uri $f.u -OutFile $p } else { Write-Host ('已有 '+$f.n) } }"
if errorlevel 1 (
  echo [错误] 模型下载失败。可重跑本脚本，或检查网络后把报错发群。
  goto :fail
)

echo.
echo === 完成 ===
echo Deep-Live-Cam 目录:
echo   %DLC_DIR%
if /I "%FSS_DLC_NOPAUSE%"=="1" goto :nested_ok
echo.
echo 下一步:
echo 1^) 若没有 ffmpeg: winget install ffmpeg ，然后新开终端
echo 2^) 可先试跑:   cd /d "%DLC_DIR%" ^&^& venv\Scripts\activate ^&^& python run.py
echo 3^) 不必手填路径：双击 scripts\setup-all-win.bat ，会写入设置并在桌面创建「打开换脸」
echo 4^) 本机无独显，换脸会很慢，先验证能开窗/出首帧即可
echo.
pause
exit /b 0

:nested_ok
echo [OK] Deep-Live-Cam 已就绪，交给一键安装继续写设置。
exit /b 0

:fail
if /I "%FSS_DLC_NOPAUSE%"=="1" exit /b 1
echo.
echo 窗口会停住，方便查看上面的错误。按任意键关闭。
pause
exit /b 1
