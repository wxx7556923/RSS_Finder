@echo off
setlocal
cd /d "%~dp0"

echo.
echo Paper Radar Windows Native Installer
echo.
echo This version does not use WSL.
echo It needs Python 3.10 or newer for Windows.
echo Python packages will be installed from local wheels when available.
echo.

call :find_python
if errorlevel 1 goto no_python

echo Found Python:
%PYTHON_CMD% --version
echo.

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo Python 3.10 or newer is required.
  echo Current Python is too old. Install a newer Python from:
  echo https://www.python.org/downloads/windows/
  echo.
  pause
  exit /b 1
)

call :check_writable
if errorlevel 1 goto not_writable

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv.
    pause
    exit /b 1
  )
)

set "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"
set "PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn"
set "PIP_CONFIG_FILE=NUL"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "http_proxy="
set "https_proxy="
set "ALL_PROXY="
set "all_proxy="
set "NO_PROXY=*"
set "no_proxy=*"

echo Installing Python packages...
if exist "wheels\*.whl" (
  echo Found local wheels. Installing without internet...
  ".venv\Scripts\python.exe" -m pip --isolated install --no-index --find-links wheels -r requirements.txt
  if errorlevel 1 goto offline_install_failed
) else (
  echo No local wheels directory found. Installing from Tsinghua PyPI mirror...
  ".venv\Scripts\python.exe" -m pip --isolated install --retries 3 --timeout 30 -i %PIP_INDEX_URL% --trusted-host %PIP_TRUSTED_HOST% -r requirements.txt
  if errorlevel 1 goto install_failed
)

if not exist ".env" (
  if exist ".env.example" copy ".env.example" ".env" >nul
)
if not exist "data" mkdir data
if not exist "output" mkdir output
if not exist "logs" mkdir logs

echo.
echo Source selection. Press Enter to keep defaults.
".venv\Scripts\python.exe" tools\configure_sources.py
if errorlevel 1 goto install_failed

echo.
echo API key setup. Press Enter to skip.
".venv\Scripts\python.exe" tools\configure_env.py
if errorlevel 1 goto install_failed

echo.
echo Install complete.
echo Next time, double-click Windows-Start.bat.
echo.
pause
exit /b 0

:find_python
set "PYTHON_CMD="
py -3 --version >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=py -3"
  exit /b 0
)
python --version >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=python"
  exit /b 0
)
python3 --version >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=python3"
  exit /b 0
)
exit /b 1

:check_writable
if not exist "config\app.yml" (
  echo Missing config\app.yml.
  exit /b 1
)
> ".paper-radar-write-test.tmp" echo test
if errorlevel 1 exit /b 1
del ".paper-radar-write-test.tmp" >nul 2>nul
copy /y "config\app.yml" "config\.paper-radar-write-test.tmp" >nul
if errorlevel 1 exit /b 1
del "config\.paper-radar-write-test.tmp" >nul 2>nul
exit /b 0

:not_writable
echo.
echo This PaperRadar folder is not writable.
echo Current folder:
echo %CD%
echo.
echo Please fully extract the zip, then move the extracted PaperRadar folder to a normal writable folder, for example:
echo   Desktop\PaperRadar
echo   Downloads\PaperRadar
echo   C:\PaperRadar
echo.
echo Do not run it from WeChat/QQ file cache, a zip preview window, or a protected system folder.
echo After moving it, double-click Windows-Install.bat again.
echo.
pause
exit /b 1

:no_python
echo Python was not found.
echo.
echo Please install Python for Windows first:
echo https://www.python.org/downloads/windows/
echo.
echo During installation, enable:
echo Add python.exe to PATH
echo.
echo After installing Python, reopen this folder and run Windows-Install.bat again.
echo.
pause
exit /b 1

:install_failed
echo.
echo Install failed. Check the message above.
echo If it says Permission denied, move the extracted PaperRadar folder to Desktop, Downloads, or C:\PaperRadar, then run Windows-Install.bat again.
echo No usable local wheels were found, so the installer tried Tsinghua PyPI mirror.
echo It also ignores user pip proxy config with PIP_CONFIG_FILE=NUL and pip --isolated.
echo If it says connection refused or Cannot connect to proxy, the network/proxy is blocking Python package download.
echo Try another network, mobile hotspot, or ask the maintainer for a package with wheels included.
echo.
pause
exit /b 1

:offline_install_failed
echo.
echo Offline install failed. The bundled wheels may not match this Python version or Windows architecture.
echo Please install 64-bit Python 3.10, 3.11, 3.12, or 3.13, then run Windows-Install.bat again.
echo If it still fails, ask the maintainer to rebuild the Windows package with matching wheels.
echo.
pause
exit /b 1
