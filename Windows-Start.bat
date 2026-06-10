@echo off
setlocal
chcp 65001 >nul
set "SCRIPT=%~dp0windows\start.bat"

if not exist "%SCRIPT%" (
  echo 没有找到 windows\start.bat。
  echo.
  echo 请先完整解压 zip 文件，不要在压缩包预览窗口里直接双击。
  echo 建议右键 zip，选择“全部解压”，然后进入解压后的 PaperRadar 文件夹。
  echo.
  pause
  exit /b 1
)

call "%SCRIPT%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo 启动未完成。请先运行 Windows-Install.bat，或按窗口提示处理。
  pause
)
exit /b %RC%
