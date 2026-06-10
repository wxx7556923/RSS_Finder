@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Paper Radar is not installed yet.
  echo Run Windows-Install.bat first.
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" tools\windows_server.py start
if errorlevel 1 (
  echo.
  echo Startup failed. Run Windows-Logs.bat and send a screenshot if needed.
  echo.
  pause
  exit /b 1
)

start "" http://127.0.0.1:8090/?mode=original
exit /b 0
