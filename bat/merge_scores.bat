@echo off
REM ============================================================
REM  Merge a filled scores JSON (from Claude web or the agent)
REM  into management_trust.json + red_flags.json and rebuild the
REM  downloadable findings reports. Overall score + verdict are
REM  recomputed automatically so everything stays consistent.
REM
REM  Usage:  merge_scores.bat path\to\reply.json
REM  Default if no arg: prompt_outputs\_scores_to_merge.json
REM ============================================================
cd /d "%~dp0.."
set "FILE=%~1"
if "%FILE%"=="" set "FILE=prompt_outputs\_scores_to_merge.json"
if not exist "%FILE%" (
  echo File not found: %FILE%
  echo Usage: merge_scores.bat path\to\reply.json
  pause
  exit /b 1
)
python scripts\score_companies.py merge "%FILE%"
pause
