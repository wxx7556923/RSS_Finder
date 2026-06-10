@echo off
setlocal
set "SCRIPT=%~dp0windows\start.bat"

if not exist "%SCRIPT%" (
  echo Missing windows\start.bat.
  echo.
  echo Please fully extract the zip file first.
  echo Do not run this file from the zip preview window.
  echo Right-click the zip, choose Extract All, then open the extracted PaperRadar folder.
  echo.
  pause
  exit /b 1
)

call "%SCRIPT%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo Startup did not finish. Run Windows-Install.bat first, or follow the message above.
  pause
)
exit /b %RC%
