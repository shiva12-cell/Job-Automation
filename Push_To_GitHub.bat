@echo off
title AutoJob AI - Push to GitHub
cd /d "C:\Users\abcom\Downloads\Job"
set "PATH=C:\Users\abcom\AppData\Local\Microsoft\WinGet\Packages\Git.MinGit_Microsoft.Winget.Source_8wekyb3d8bbwe\cmd;%PATH%"

echo ============================================================
echo   Pushing AutoJob AI Code to GitHub: shiva12-cell/autojob-ai
echo ============================================================
echo.
git push -u origin main
echo.
if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] Code pushed successfully to https://github.com/shiva12-cell/autojob-ai !
) else (
    echo [NOTE] If you were prompted for a password, GitHub requires a Personal Access Token (PAT).
    echo Generate one at: https://github.com/settings/tokens
)
echo.
pause
