@echo off
setlocal
set "ROOT=%~dp0.."
set "URL=http://localhost:8090/?mode=original"

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
  echo Ubuntu is not initialized yet, or Windows needs a restart.
  echo Restart Windows, open Ubuntu once, create a username and password, then run this again.
  pause
  exit /b 1
)

wsl.exe -d "%DISTRO%" -e bash -lc "cd \"$(wslpath '%ROOT%')\" && PAPER_RADAR_OPEN=0 bash paper-radar start"
if errorlevel 1 (
  echo.
  echo Startup failed. Run Windows-Logs.bat to inspect logs.
  pause
  exit /b 1
)

echo Waiting for the local web service...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$u='%URL%'; $ok=$false; for($i=0; $i -lt 30; $i++){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 2; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 500){ $ok=$true; break } } catch { Start-Sleep -Seconds 1 } }; if($ok){ exit 0 } else { exit 1 }" >nul 2>nul
if errorlevel 1 (
  echo.
  echo The service was started, but Windows cannot access %URL% yet.
  echo Run Windows-Logs.bat, or wait 10 seconds and run Windows-Start.bat again.
  pause
  exit /b 1
)

start "" %URL%
