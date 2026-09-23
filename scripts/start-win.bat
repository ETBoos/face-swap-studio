@echo off
REM FaceSwap Studio — Windows launcher.
REM Starts pythonw.exe in a separate process and exits this console.
REM pythonw has no console, so closing a terminal cannot close the GUI.
REM Success: no pause (the console should go away).
REM Failure: pause so a double-click does not flash closed.
chcp 65001 >nul
setlocal EnableExtensions

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "ROOT=%CD%"

set "PYW="
if exist "%ROOT%\.venv\Scripts\pythonw.exe" set "PYW=%ROOT%\.venv\Scripts\pythonw.exe"

if not defined PYW (
  where py >nul 2>&1
  if not errorlevel 1 (
    for /f "usebackq delims=" %%I in (`py -3 -c "import pathlib,sys; p=pathlib.Path(sys.executable); w=p.with_name('pythonw.exe'); print(w if w.is_file() else '')"`) do set "PYW=%%I"
  )
)

if not defined PYW (
  where python >nul 2>&1
  if not errorlevel 1 (
    for /f "usebackq delims=" %%I in (`python -c "import pathlib,sys; p=pathlib.Path(sys.executable); w=p.with_name('pythonw.exe'); print(w if w.is_file() else '')"`) do set "PYW=%%I"
  )
)

if not defined PYW goto :fail_pyw

set "PYEXE=%PYW:pythonw.exe=python.exe%"
if not exist "%PYEXE%" goto :fail_py

set "PYTHONPATH=%ROOT%\src"
"%PYEXE%" -c "import face_swap_studio.ui.main_window"
if errorlevel 1 goto :fail_import

REM Empty title is required so start treats the quoted exe as the program.
start "" "%PYW%" -m face_swap_studio
if errorlevel 1 goto :fail_start
exit /b 0

:fail_pyw
echo [错误] 未找到 pythonw.exe。请先双击 scripts\setup-all-win.bat
echo [Error] pythonw.exe was not found. Run scripts\setup-all-win.bat first.
goto :fail

:fail_py
echo [错误] 找到了 pythonw.exe，但旁边没有 python.exe，无法显示启动错误。
echo [Error] python.exe next to pythonw.exe is missing, so launch errors cannot be shown.
goto :fail

:fail_import
echo.
echo [错误] FaceSwap Studio 无法启动（导入失败）。请把上面的报错截图发来。
echo [Error] Failed to import face_swap_studio. See the message above.
goto :fail

:fail_start
echo [错误] 启动失败。pythonw 没有跑起来。
echo [Error] Could not start pythonw.
goto :fail

:fail
echo.
echo 窗口会停住，方便查看上面的错误。按任意键关闭。
pause
exit /b 1
