@echo off
setlocal
set "SCRIPT=%~dp0windows\stop.bat"

if not exist "%SCRIPT%" (
  echo Missing windows\stop.bat.
  echo.
  echo Please fully extract the zip file first.
  echo Do not run this file from the zip preview window.
  echo.
  pause
  exit /b 1
)

call "%SCRIPT%"
exit /b %ERRORLEVEL%
