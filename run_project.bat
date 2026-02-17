@echo off
setlocal

REM Change to the directory of this script
cd /d "%~dp0"

REM ----------------------------------------------------------------------
REM Locate a base Python interpreter to create the virtual environment.
REM You can hard-code a path here if needed, e.g.:
REM   set "PYTHON_EXE=C:\Python311\python.exe"
REM If left empty, we will try: .venv\Scripts\python.exe, py, then python.
REM ----------------------------------------------------------------------
set "PYTHON_EXE="

REM If venv already exists, prefer its python for subsequent commands
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
)

REM If PYTHON_EXE still not set, try py launcher
if not defined PYTHON_EXE (
    where py >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=py -3"
    )
)

REM If still not set, try plain python on PATH
if not defined PYTHON_EXE (
    where python >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
    )
)

REM If we still don't have a Python interpreter, abort with a clear message
if not defined PYTHON_EXE (
    echo Could not find Python on this system.
    echo Please install Python or set PYTHON_EXE to the full path of python.exe in this script.
    pause
    exit /b 1
)

REM ----------------------------------------------------------------------
REM Create virtual environment if it does not exist
REM ----------------------------------------------------------------------
if not exist ".venv" (
    echo Creating virtual environment in .venv ...
    %PYTHON_EXE% -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment. Check that the Python path is correct.
        pause
        exit /b 1
    )
)

REM Use the venv's python from here on
set "VENV_PY=.venv\Scripts\python.exe"

REM Upgrade pip and install dependencies
echo Installing/Updating required packages ...
"%VENV_PY%" -m pip install --upgrade pip
if exist "requirements.txt" (
    "%VENV_PY%" -m pip install -r requirements.txt
) else (
    echo requirements.txt not found, skipping dependency installation.
)

REM Run the main trade copier script
echo Starting mt5_connect.py ...
"%VENV_PY%" mt5_connect.py

echo Script finished.
pause

