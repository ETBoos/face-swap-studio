@echo off
REM Calls setup-all-win.bat and always pauses, even if that script returns.
REM Use this when a double-click of setup-all-win.bat still flashes closed.
chcp 65001 >nul
setlocal EnableExtensions
title FaceSwap Studio 一键安装（调试，窗口保持打开）
echo 调试入口：调用 setup-all-win.bat，结束时一定会 pause。
echo.
call "%~dp0setup-all-win.bat"
set "RC=%ERRORLEVEL%"
echo.
echo setup-all-win.bat 结束，错误码 %RC%
echo 按任意键关闭。
pause
exit /b %RC%
