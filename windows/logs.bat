@echo off
setlocal
set "ROOT=%~dp0.."

where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo WSL was not detected. Run Windows-Install.bat first.
  pause
  exit /b 1
)

wsl.exe bash -lc "echo WSL_READY" >nul 2>nul
if errorlevel 1 (
  echo Ubuntu is not initialized yet. Restart Windows, open Ubuntu once, and create a username and password.
  pause
  exit /b 1
)

wsl.exe bash -lc "cd \"$(wslpath '%ROOT%')\" && mkdir -p logs && tail -n 120 logs/web.log logs/app.log 2>/dev/null || true"
pause
