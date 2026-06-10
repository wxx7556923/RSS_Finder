@echo off
setlocal
set "ROOT=%~dp0.."

where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo WSL was not detected. Run Windows-Install.bat first.
  pause
  exit /b 1
)

set "DISTRO="
for /f "usebackq delims=" %%D in (`powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$names = (wsl.exe --list --quiet 2^>$null) -replace [char]0,''; $match = $names -split '[\r\n]+' ^| Where-Object { $_ -match '^Ubuntu' } ^| Select-Object -First 1; if($match){ $match.Trim() }"`) do set "DISTRO=%%D"
if not defined DISTRO (
  echo No installed Ubuntu distribution was detected. Run Windows-Install.bat first.
  pause
  exit /b 1
)

wsl.exe -d "%DISTRO%" -e sh -lc "echo WSL_READY" >nul 2>nul
if errorlevel 1 (
  echo Ubuntu is not initialized yet. Restart Windows, open Ubuntu once, and create a username and password.
  pause
  exit /b 1
)

wsl.exe -d "%DISTRO%" -e bash -lc "cd \"$(wslpath '%ROOT%')\" && mkdir -p logs && tail -n 120 logs/web.log logs/app.log 2>/dev/null || true"
pause
