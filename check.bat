@echo off
title The Invoice Wizard - Requirements Check
echo.
echo  ============================================
echo   The Invoice Wizard - Requirements Check
echo  ============================================
echo.

set ALL_OK=1

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [MISSING]  Python ............. not installed or not in PATH
    set ALL_OK=0
) else (
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do (
        echo  [OK]       Python ............. %%v
    )
)

echo.
echo  Checking required packages:
echo.

call :check pdfplumber   pdfplumber
call :check openpyxl     openpyxl
call :check fastapi      fastapi
call :check uvicorn      uvicorn
call :check multipart    python-multipart
call :check jinja2       jinja2

echo.
echo  --------------------------------------------
if "%ALL_OK%"=="1" (
    echo.
    echo   All requirements are installed.
    echo   You are ready to go!
    echo   Double-click start.bat to open the app.
) else (
    echo.
    echo   Some items are missing.
    echo   Double-click install.bat to fix this,
    echo   then run check.bat again to confirm.
)
echo.
pause
goto :eof

:check
python -c "import %1" >nul 2>&1
if errorlevel 1 (
    echo  [MISSING]  %2
    set ALL_OK=0
) else (
    echo  [OK]       %2
)
goto :eof
