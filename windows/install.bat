@echo off
setlocal
set "ROOT=%~dp0.."

where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo 未检测到 WSL。
  echo 请先用管理员 PowerShell 运行：wsl --install -d Ubuntu
  echo 安装完成后重启电脑，并先打开一次 Ubuntu 完成用户名和密码设置。
  pause
  exit /b 1
)

echo 正在检查 WSL Ubuntu...
wsl.exe -l -q >nul 2>nul
if errorlevel 1 (
  echo.
  echo WSL 已存在，但还没有可用的 Ubuntu 发行版。
  echo 请先用管理员 PowerShell 运行：wsl --install -d Ubuntu
  echo 安装完成后重启电脑，并先打开一次 Ubuntu 完成用户名和密码设置。
  pause
  exit /b 1
)

wsl.exe bash -lc "echo WSL_READY" >nul 2>nul
if errorlevel 1 (
  echo.
  echo Ubuntu 还没有初始化完成，或者电脑需要重启。
  echo 请重启电脑，然后从开始菜单打开 Ubuntu，完成用户名和密码设置后再运行本脚本。
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
