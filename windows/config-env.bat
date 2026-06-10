@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo Paper Radar is not installed yet.
  echo Run Windows-Install.bat first.
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" tools\configure_env.py
echo.
pause
