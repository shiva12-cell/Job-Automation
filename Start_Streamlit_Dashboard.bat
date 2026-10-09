@echo off
title AutoJob AI - Streamlit Command Center
cd /d "C:\Users\abcom\Downloads\Job"
echo ============================================================
echo   Starting AutoJob AI Streamlit Dashboard...
echo ============================================================
echo.
echo Launching Streamlit on http://localhost:8501 ...
".\.venv\Scripts\python.exe" -m streamlit run streamlit_app.py
pause
