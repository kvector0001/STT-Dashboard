@echo off
cd /d "%~dp0"
title Portfolio - Morning Refresh & Push
echo ============================================
echo   PORTFOLIO MORNING REFRESH
echo ============================================
echo.

echo [1/4] Fetching latest prices from Google Sheet + Yahoo...
python scripts/fetch_prices.py
if errorlevel 1 (
    echo.
    echo ERROR: Price fetch failed. Check the messages above.
    pause
    exit /b 1
)
echo.

echo [2/4] Syncing with GitHub (pulling any bot commits)...
git stash --include-untracked 2>nul
git pull origin main --no-edit
git stash pop 2>nul

echo.
echo [3/4] Staging and committing data...
git add prices.json stocks.json data/portfolio.xlsx
git commit -m "chore: manual morning refresh %date% %time%"
if errorlevel 1 (
    echo No changes to commit - data already up to date.
)

echo.
echo [4/4] Pushing to GitHub...
git push origin main
if errorlevel 1 (
    echo.
    echo ERROR: Push failed. You may need to resolve conflicts manually.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   DONE! Live site will update in ~2 minutes.
echo   https://kvector0001.github.io/STT-Dashboard/
echo ============================================
echo.
echo This window will close in 10 seconds...
timeout /t 10 >nul
