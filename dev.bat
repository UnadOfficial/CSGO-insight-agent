@echo off
setlocal
cd /d "%~dp0"
echo CSGO Insight Agent - one-click desktop:dev (no installer)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\windows\dev_desktop.ps1" %*
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo.
  echo Start failed, exit code %ERR%.
  echo See docs\dev-setup.zh-CN.md if the environment is incomplete.
  pause
)
exit /b %ERR%
