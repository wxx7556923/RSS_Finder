@echo off
setlocal
set "ROOT=%~dp0.."

wsl.exe bash -lc "cd \"$(wslpath '%ROOT%')\" && if [ ! -x .venv/bin/python ]; then bash install.sh; fi && .venv/bin/python tools/configure_env.py"
pause
