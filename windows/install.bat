@echo off
setlocal
set "ROOT=%~dp0.."

echo.
echo Paper Radar Windows 安装向导
echo.
echo 只需要记住：如果中途重启、弹出 Ubuntu、或者设置完用户名密码，
echo 都回到这个文件夹，再双击 Windows-Install.bat 继续。
echo.

where wsl.exe >nul 2>nul
if errorlevel 1 (
  call :install_wsl
  exit /b 1
)

wsl.exe -l -q | findstr /R "." >nul 2>nul
if errorlevel 1 (
  echo 未检测到已安装的 Ubuntu。
  call :install_wsl
  exit /b 1
)

wsl.exe bash -lc "echo WSL_READY" >nul 2>nul
if errorlevel 1 (
  echo.
  echo WSL/Ubuntu 已安装，但 Ubuntu 还没有完成第一次初始化。
  echo.
  echo 我会尝试打开 Ubuntu 窗口。请在 Ubuntu 窗口里创建用户名和密码。
  echo 注意：输入密码时屏幕不会显示字符，这是正常的。
  echo.
  echo 完成后关闭 Ubuntu 窗口，再回到这个文件夹双击 Windows-Install.bat。
  echo.
  start "" wsl.exe
  pause
  exit /b 1
)

echo 正在检查 WSL Ubuntu...
wsl.exe bash -lc "echo WSL_READY" >nul 2>nul
if errorlevel 1 (
  echo.
  echo Ubuntu 还没有初始化完成，或者电脑需要重启。
  echo 请重启电脑，然后回到这个文件夹，再双击 Windows-Install.bat。
  pause
  exit /b 1
)

echo 正在 WSL Ubuntu 里安装 Paper Radar...
wsl.exe bash -lc "cd \"$(wslpath '%ROOT%')\" && bash install.sh && .venv/bin/python tools/configure_sources.py && .venv/bin/python tools/configure_env.py"
if errorlevel 1 (
  echo.
  echo 安装失败。请查看上面的错误信息。
  pause
  exit /b 1
)

echo.
echo 安装完成。
echo 以后启动请双击 Windows-Start.bat。
pause
exit /b 0

:install_wsl
echo.
echo 这台电脑还不能直接运行 Paper Radar，需要先安装 WSL Ubuntu。
echo 这是微软官方的 Linux 环境，Paper Radar 会在里面运行。
echo.
choice /C YN /M "是否现在打开管理员窗口安装 WSL Ubuntu"
if errorlevel 2 (
  echo.
  echo 你选择了不安装。以后可以重新双击 Windows-Install.bat。
  pause
  exit /b 1
)
echo.
echo 接下来会弹出管理员权限窗口，请选择“是”。
echo 如果安装结束后 Windows 提示重启，请重启电脑。
echo 重启后回到这个文件夹，再双击 Windows-Install.bat 继续。
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -Verb RunAs -FilePath wsl.exe -ArgumentList '--install -d Ubuntu'"
echo.
echo 已请求安装 WSL Ubuntu。
echo 如果弹出的窗口提示重启，请重启；重启后继续双击 Windows-Install.bat。
echo 如果弹出 Ubuntu 设置窗口，请创建用户名和密码；完成后继续双击 Windows-Install.bat。
pause
exit /b 1
