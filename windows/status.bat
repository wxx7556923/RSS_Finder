@echo off
setlocal
set "ROOT=%~dp0.."

where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo 未检测到 WSL。请先运行 Windows-Install.bat。
  pause
  exit /b 1
)

wsl.exe bash -lc "echo WSL_READY" >nul 2>nul
if errorlevel 1 (
  echo Ubuntu 还没有初始化完成。请重启电脑，并先打开一次 Ubuntu 完成用户名和密码设置。
  pause
  exit /b 1
)

wsl.exe bash -lc "cd \"$(wslpath '%ROOT%')\" && bash paper-radar status"
pause
