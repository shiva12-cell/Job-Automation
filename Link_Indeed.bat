@echo off
title Link Indeed Account - AutoJob AI
cd /d "C:\Users\abcom\Downloads\Job"
echo ============================================================
echo   INDEED (INDIA) MANUAL 1-TIME SESSION LOGIN
echo ============================================================
echo.
echo Opening Chrome for you to log into Indeed...
echo Once you log in completely and see your Indeed feed,
echo come back to this window and press ENTER to save!
echo.
".\.venv\Scripts\python.exe" src/applier/indeed_manual_login.py
pause
