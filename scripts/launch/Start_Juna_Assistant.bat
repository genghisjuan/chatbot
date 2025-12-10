@echo off
:: Juna Assistant Launcher
:: This script launches the GUI controller for the Juna Assistant server

:: Change to project root (two levels up from scripts/launch/)
cd /d "%~dp0..\.."
if errorlevel 1 (
    echo ERROR: Failed to change to project directory
    pause
    exit /b 1
)

:: Verify Python is installed and in PATH
where pythonw >nul 2>&1
if errorlevel 1 (
    echo ERROR: pythonw.exe not found in PATH
    echo.
    echo Please ensure Python is installed and added to your system PATH
    echo You can download Python from: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Verify launcher script exists
if not exist "scripts\launch\launcher.py" (
    echo ERROR: launcher.py not found!
    echo.
    echo Expected location: %CD%\scripts\launch\launcher.py
    echo Current directory: %CD%
    pause
    exit /b 1
)

:: Launch the Assistant (Windowless) from root directory
start "Juna Assistant" pythonw "scripts\launch\launcher.py"

:: Exit with success code
exit /b 0
