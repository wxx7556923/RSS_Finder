@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" tools\windows_server.py logs
) else (
  if exist "logs\web.log" type "logs\web.log"
  if not exist "logs\web.log" echo No log file found.
)
echo.
pause
