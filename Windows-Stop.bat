@echo off
setlocal
chcp 65001 >nul
set "SCRIPT=%~dp0windows\stop.bat"

if not exist "%SCRIPT%" (
  echo 没有找到 windows\stop.bat。
  echo.
  echo 请先完整解压 zip 文件，不要在压缩包预览窗口里直接双击。
  echo.
  pause
  exit /b 1
)

call "%SCRIPT%"
exit /b %ERRORLEVEL%
