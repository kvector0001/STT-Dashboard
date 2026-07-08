@echo off
cd /d "%~dp0.."
git add .
git commit -m "Add: Catalyst events analysis feature with GPT integration to Deep Analysis cards; Fix: Extended historical data fetch to 5y for 6M/3Y/5Y returns; Tab swap prioritizing Deep Analysis view"
git push origin main
