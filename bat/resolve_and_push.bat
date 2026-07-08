@echo off
cd /d "%~dp0.."
REM Resolve conflicts by keeping our local versions
git checkout --ours prices.json
git checkout --ours data/portfolio.xlsx
git checkout --ours stocks.json
git add .
git commit -m "Merge: Resolve conflicts - keep local versions of generated files"
git push origin main
