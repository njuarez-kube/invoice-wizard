@echo off
title The Invoice Wizard — Create Desktop Shortcut

:: Get the folder where this script lives (the app folder)
set APP_DIR=%~dp0
set APP_DIR=%APP_DIR:~0,-1%

echo.
echo  Creating desktop shortcut...

powershell -NoProfile -Command ^
  "$WshShell = New-Object -comObject WScript.Shell;" ^
  "$lnk = $WshShell.CreateShortcut([System.Environment]::GetFolderPath('Desktop') + '\The Invoice Wizard.lnk');" ^
  "$lnk.TargetPath = '%APP_DIR%\start.bat';" ^
  "$lnk.WorkingDirectory = '%APP_DIR%';" ^
  "$lnk.Description = 'The Invoice Wizard — click to start';" ^
  "$lnk.IconLocation = '%APP_DIR%\icon.ico';" ^
  "$lnk.WindowStyle = 1;" ^
  "$lnk.Save()"

echo.
echo  Done! A shortcut called "The Invoice Wizard" has been
echo  added to your Desktop.
echo.
pause
