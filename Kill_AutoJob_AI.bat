@echo off
title Kill Switch - AutoJob AI
echo ============================================================
echo   ACTIVATING AUTOJOB AI KILL SWITCH
echo ============================================================
echo.
echo Terminating all AutoJob AI processes, background workers, and browsers...
taskkill /F /FI "WINDOWTITLE eq AutoJob AI*" /T >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo.
echo [OK] AutoJob AI completely stopped.
echo Next time you launch, a fresh pipeline cycle will run from the start.
echo.
pause
