@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" tools\windows_server.py status
) else (
  echo Paper Radar is not installed yet.
)
echo.
pause
