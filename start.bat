@echo off
title The Invoice Wizard
echo.
echo  ============================================
echo   The Invoice Wizard is starting...
echo   Your browser will open automatically.
echo.
echo   DO NOT close this window while using
echo   the app — it keeps the server running.
echo.
echo   To stop: close this window, or press
echo   Ctrl+C and confirm with Y + Enter.
echo  ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found.
    echo  Please run install.bat first.
    echo.
    pause
    exit /b 1
)

python main.py

echo.
echo  The app has stopped.
pause
