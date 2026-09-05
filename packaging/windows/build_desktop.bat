@echo off
setlocal
cd /d "%~dp0\..\.."
if "%~1"=="" (
  echo Usage: build_desktop.bat ^<x.y.z^> [--full]
  echo Example: build_desktop.bat 2.6.0
  echo          build_desktop.bat 2.6.0 --full
  exit /b 1
)
set "VERSION=%~1"
set "FULL="
if /I "%~2"=="--full" set "FULL=-Full"
if /I "%~2"=="-Full" set "FULL=-Full"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_desktop.ps1" -Version "%VERSION%" %FULL%
exit /b %errorlevel%
