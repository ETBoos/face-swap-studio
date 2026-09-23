@echo off
REM FaceSwap Studio — Windows launcher.
REM Starts pythonw.exe in a separate process and exits this console.
REM pythonw has no console, so closing a terminal cannot close the GUI.
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

if not defined PYW (
  echo [错误] 未找到 pythonw.exe。请先双击 scripts\setup-all-win.bat
  echo [Error] pythonw.exe was not found. Run scripts\setup-all-win.bat first.
  pause
  exit /b 1
)

REM Empty title is required so start treats the quoted exe as the program.
start "" "%PYW%" -m face_swap_studio
exit /b 0
