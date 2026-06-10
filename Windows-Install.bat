@echo off
setlocal
set "SCRIPT=%~dp0windows\install.bat"

if not exist "%SCRIPT%" (
  echo Missing windows\install.bat.
  echo.
  echo Please fully extract the zip file first.
  echo Do not run this file from the zip preview window.
  echo Right-click the zip, choose Extract All, then open the extracted PaperRadar folder.
  echo.
  pause
  exit /b 1
)

echo Starting Paper Radar installer...
echo.
call "%SCRIPT%"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo.
  echo The installer stopped or did not finish.
  echo Follow the message above, then run Windows-Install.bat again.
  echo If you are unsure, send a screenshot of this window to the maintainer.
) else (
  echo Installer finished. If it says install complete above, use Windows-Start.bat next time.
)
echo.
pause
exit /b %RC%
