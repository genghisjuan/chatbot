@echo off
REM Quick push script for Git
REM Usage: push "your commit message"

cd /d %~dp0

"C:\Program Files\Git\bin\git.exe" add .
"C:\Program Files\Git\bin\git.exe" commit -m "%*"
"C:\Program Files\Git\bin\git.exe" push

echo.
echo ✓ Changes pushed to GitHub!
echo Railway will auto-deploy in ~2 minutes
pause
