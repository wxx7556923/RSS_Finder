@echo off
setlocal
set "ROOT=%~dp0.."

wsl.exe bash -lc "cd \"$(wslpath '%ROOT%')\" && bash paper-radar status"
pause
