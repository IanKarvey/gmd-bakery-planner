@echo off
rem GMD Bakery Planner launcher - installs matplotlib if missing, then starts the app.
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

%PY% -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo This Python was installed without Tk, which the program needs for its window.
    echo Re-run the Python installer, choose Modify, and tick "tcl/tk and IDLE".
    pause
    exit /b 1
)

%PY% -c "import matplotlib" >nul 2>&1
if errorlevel 1 (
    echo Installing required library ^(matplotlib^)... this needs internet, once only.
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Install failed. Check your internet connection and try again.
        pause
        exit /b 1
    )
)

%PY% bakery_planner.py
if errorlevel 1 pause
