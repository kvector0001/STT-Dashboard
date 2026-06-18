@echo off
REM ============================================================
REM  Find holdings missing a Management Trust / Red Flags score
REM  and open a ready-to-fill worklist. No API key needed.
REM ============================================================
cd /d "%~dp0"
python scripts\score_companies.py pending
echo.
echo ============================================================
echo  NEXT STEP - pick one:
echo.
echo  [A] VS Code agent mode (recommended, no API key):
echo      open this folder in VS Code, then in Copilot Chat
echo      (Agent mode) type:   /score-pending
echo      The agent scores every pending holding and saves it.
echo.
echo  [B] Claude web:
echo      paste blocks from _pending_scores_worklist.md into Claude,
echo      collect answers into prompt_outputs\_scores_to_merge.json
echo      (shape: prompt_outputs\_scores_to_merge.template.json),
echo      then run:   merge_scores.bat prompt_outputs\_scores_to_merge.json
echo ============================================================
start "" code "%~dp0prompt_outputs\_pending_scores_worklist.md" 2>nul
pause
