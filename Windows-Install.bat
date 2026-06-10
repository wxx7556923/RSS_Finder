@echo off
setlocal
chcp 65001 >nul
set "SCRIPT=%~dp0windows\install.bat"

if not exist "%SCRIPT%" (
  echo 没有找到 windows\install.bat。
  echo.
  echo 请先完整解压 zip 文件，不要在压缩包预览窗口里直接双击。
  echo 建议右键 zip，选择“全部解压”，然后进入解压后的 PaperRadar 文件夹。
  echo.
  pause
  exit /b 1
)

echo 正在启动安装向导...
echo.
call "%SCRIPT%"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo.
  echo 安装向导已暂停或未完成。请按窗口提示处理后，再双击 Windows-Install.bat。
  echo 如果你不知道发生了什么，请把这个窗口截图发给维护者。
) else (
  echo 安装向导已结束。如果上面显示“安装完成”，以后双击 Windows-Start.bat。
)
echo.
pause
exit /b %RC%
