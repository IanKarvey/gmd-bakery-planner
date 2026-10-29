@echo off
rem Builds the no-install version (dist\GMD Bakery Planner\). Needs Python and internet once, on the building PC only.
cd /d "%~dp0"
set PY=python
%PY% --version >nul 2>&1
if errorlevel 1 set PY=py
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed. Download it from https://www.python.org/downloads/
    pause
    exit /b 1
)
%PY% -c "import matplotlib, PIL" >nul 2>&1
if errorlevel 1 %PY% -m pip install -r requirements.txt
%PY% build_exe.py
pause
