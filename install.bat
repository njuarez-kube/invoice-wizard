@echo off
title The Invoice Wizard — Installation
echo.
echo  ============================================
echo   The Invoice Wizard — First-time setup
echo  ============================================
echo.

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python is not installed on this computer.
    echo.
    echo  Please follow these steps:
    echo    1. Go to https://www.python.org/downloads/
    echo    2. Click the big Download button
    echo    3. Run the installer
    echo    4. IMPORTANT: check "Add Python to PATH" before clicking Install
    echo    5. Once installed, double-click install.bat again
    echo.
    pause
    exit /b 1
)

echo  Python found. Installing required packages...
echo  (This may take a minute — please wait)
echo.

pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo  ERROR: Installation failed.
    echo  Make sure you are connected to the internet and try again.
    echo.
    pause
    exit /b 1
)

echo.
echo  Verifying installation...
echo.
call "%~dp0check.bat"
