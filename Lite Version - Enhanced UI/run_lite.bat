@echo off
rem Starts the simple version (bakery_lite.py). Installs matplotlib first if it is missing.
cd /d "%~dp0"
set PY=python
%PY% --version >nul 2>&1
if errorlevel 1 set PY=py
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed. Download it from https://www.python.org/downloads/
    echo During setup, tick "Add python.exe to PATH" and "tcl/tk and IDLE".
    pause
    exit /b 1
)
%PY% -c "import matplotlib" >nul 2>&1
if errorlevel 1 (
    echo Installing matplotlib, this needs internet, once only...
    %PY% -m pip install matplotlib
    if errorlevel 1 (
        echo Install failed. Check your internet connection and try again.
        pause
        exit /b 1
    )
)
%PY% bakery_lite.py
if errorlevel 1 pause
