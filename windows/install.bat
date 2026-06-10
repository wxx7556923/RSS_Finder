@echo off
setlocal
set "ROOT=%~dp0.."

echo.
echo Paper Radar Windows Installer
echo.
echo Rule: after each stage, come back to this folder and run
echo Windows-Install.bat again until it says install complete.
echo.

where wsl.exe >nul 2>nul
if errorlevel 1 (
  call :install_wsl
  exit /b 1
)

wsl.exe -l -q | findstr /R "." >nul 2>nul
if errorlevel 1 (
  echo No installed Ubuntu distribution was detected.
  call :install_wsl
  exit /b 1
)

wsl.exe bash -lc "echo WSL_READY" >nul 2>nul
if errorlevel 1 (
  echo.
  echo WSL/Ubuntu is installed, but Ubuntu has not finished first-time setup.
  echo.
  echo I will try to open an Ubuntu window.
  echo Create a Ubuntu username and password there.
  echo The password will not be shown while typing. This is normal.
  echo.
  echo After Ubuntu setup is done, close Ubuntu and run Windows-Install.bat again.
  echo.
  start "" wsl.exe
  pause
  exit /b 1
)

echo Checking WSL Ubuntu...
wsl.exe bash -lc "echo WSL_READY" >nul 2>nul
if errorlevel 1 (
  echo.
  echo Ubuntu is not ready yet, or Windows needs a restart.
  echo Restart Windows, then come back to this folder and run Windows-Install.bat again.
  pause
  exit /b 1
)

echo Installing Paper Radar inside WSL Ubuntu...
wsl.exe bash -lc "cd \"$(wslpath '%ROOT%')\" && bash install.sh && .venv/bin/python tools/configure_sources.py && .venv/bin/python tools/configure_env.py"
if errorlevel 1 (
  echo.
  echo Install failed. Check the message above.
  pause
  exit /b 1
)

echo.
echo Install complete.
echo Next time, start Paper Radar with Windows-Start.bat.
pause
exit /b 0

:install_wsl
echo.
echo This computer needs WSL Ubuntu before Paper Radar can run.
echo WSL Ubuntu is Microsoft's Linux environment for Windows.
echo.
choice /C YN /M "Open an administrator window to install WSL Ubuntu now"
if errorlevel 2 (
  echo.
  echo You chose not to install now. Run Windows-Install.bat again later.
  pause
  exit /b 1
)
echo.
echo An administrator permission window should appear. Choose Yes.
echo If Windows asks for a restart, restart the computer.
echo After restart, come back to this folder and run Windows-Install.bat again.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -Verb RunAs -FilePath wsl.exe -ArgumentList '--install -d Ubuntu'"
echo.
echo WSL Ubuntu installation was requested.
echo If Windows asks for a restart, restart and then run Windows-Install.bat again.
echo If Ubuntu setup appears, create a username and password, then run Windows-Install.bat again.
pause
exit /b 1
