@echo off
rem Re-export the Android test APK. No GPU needed; runs headless.
rem Tools are installed by setup_tools.ps1. Location: %HD2D_TOOLS%, default C:\tools\hd2d.
rem Keep this file ASCII-only: cmd.exe misparses UTF-8 text here.
setlocal
if not defined HD2D_TOOLS set "HD2D_TOOLS=C:\tools\hd2d"
set "GODOT=%HD2D_TOOLS%\godot\Godot_v4.7.2-stable_win64_console.exe"
set "PROJ=%~dp0."
if not exist "%GODOT%" (
  echo Godot not found at %GODOT%
  echo Run: powershell -ExecutionPolicy Bypass -File "%~dp0setup_tools.ps1" -AcceptAndroidLicense
  exit /b 1
)
"%GODOT%" --headless --path "%PROJ%" --export-debug "Android" "build/zg_hd2d_test.apk"
if errorlevel 1 (
  echo EXPORT FAILED
  exit /b 1
)
echo.
echo DONE: %~dp0build\zg_hd2d_test.apk
