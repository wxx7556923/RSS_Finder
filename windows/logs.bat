@echo off
setlocal
set "ROOT=%~dp0.."

wsl.exe bash -lc "cd \"$(wslpath '%ROOT%')\" && mkdir -p logs && tail -n 120 logs/web.log logs/app.log 2>/dev/null || true"
pause
