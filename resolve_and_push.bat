@echo off
cd /d "c:\Users\krunal.kapadiya\OneDrive - PUMA\BACKUPS\Krunal\0. STT - Port\Dashboard"
REM Resolve conflicts by keeping our local versions
"C:\Users\krunal.kapadiya\AppData\Local\Programs\Git\bin\git.exe" checkout --ours prices.json
"C:\Users\krunal.kapadiya\AppData\Local\Programs\Git\bin\git.exe" checkout --ours data/portfolio.xlsx
"C:\Users\krunal.kapadiya\AppData\Local\Programs\Git\bin\git.exe" checkout --ours stocks.json
"C:\Users\krunal.kapadiya\AppData\Local\Programs\Git\bin\git.exe" add .
"C:\Users\krunal.kapadiya\AppData\Local\Programs\Git\bin\git.exe" commit -m "Merge: Resolve conflicts - keep local versions of generated files"
"C:\Users\krunal.kapadiya\AppData\Local\Programs\Git\bin\git.exe" push origin main
