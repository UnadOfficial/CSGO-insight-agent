@echo off
setlocal
cd /d "%~dp0\..\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev_desktop.ps1" %*
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo.
  echo [desktop:dev] exit code %ERR%. Use this script for daily work, not build_desktop.
  pause
)
exit /b %ERR%
