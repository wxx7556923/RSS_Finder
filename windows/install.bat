@echo off
setlocal
set "ROOT=%~dp0.."

where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo WSL is not installed or not available.
  echo Please install Ubuntu on WSL first: wsl --install -d Ubuntu
  pause
  exit /b 1
)

echo Installing Paper Radar in WSL...
wsl.exe bash -lc "cd \"$(wslpath '%ROOT%')\" && bash install.sh && .venv/bin/python tools/configure_sources.py && .venv/bin/python tools/configure_env.py"
if errorlevel 1 (
  echo.
  echo Install failed. Please check the message above.
  pause
  exit /b 1
)

echo.
echo Install complete.
echo You can now run windows\start.bat.
pause
