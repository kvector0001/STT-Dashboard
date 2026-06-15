@echo off
cd /d "%~dp0"
echo Starting Portfolio Dashboard...
echo Open http://localhost:8000 in your browser
echo.
echo Keep this window open while using the dashboard.
echo Close it when done.
echo.
python app.py
pause
