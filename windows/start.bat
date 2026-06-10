@echo off
setlocal
set "ROOT=%~dp0.."

where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo WSL is not installed or not available.
  pause
  exit /b 1
)

wsl.exe bash -lc "cd \"$(wslpath '%ROOT%')\" && bash paper-radar start"
if errorlevel 1 (
  echo.
  echo Start failed. Run windows\logs.bat to inspect logs.
  pause
  exit /b 1
)

start "" http://localhost:8090/?mode=original
