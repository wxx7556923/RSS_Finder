@echo off
setlocal
set "ROOT=%~dp0.."
set "URL=http://localhost:8090/?mode=original"

where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo 未检测到 WSL。请先运行 Windows-Install.bat。
  pause
  exit /b 1
)

wsl.exe bash -lc "echo WSL_READY" >nul 2>nul
if errorlevel 1 (
  echo Ubuntu 还没有初始化完成，或者电脑需要重启。
  echo 请重启电脑，然后从开始菜单打开 Ubuntu，完成用户名和密码设置后再运行本脚本。
  pause
  exit /b 1
)

wsl.exe bash -lc "cd \"$(wslpath '%ROOT%')\" && PAPER_RADAR_OPEN=0 bash paper-radar start"
if errorlevel 1 (
  echo.
  echo 启动失败。请运行 Windows-Logs.bat 查看日志。
  pause
  exit /b 1
)

echo 正在等待本地网页服务就绪...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$u='%URL%'; $ok=$false; for($i=0; $i -lt 30; $i++){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 2; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 500){ $ok=$true; break } } catch { Start-Sleep -Seconds 1 } }; if($ok){ exit 0 } else { exit 1 }" >nul 2>nul
if errorlevel 1 (
  echo.
  echo 服务已经尝试启动，但 Windows 暂时打不开 %URL%
  echo 请先运行 Windows-Logs.bat 查看日志；也可以等 10 秒后再运行 Windows-Start.bat。
  pause
  exit /b 1
)

start "" %URL%
