@echo off
rem Weekly CFTC electricity COT report. Usage: cot [URL] [--backfill N] [--open]
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%~dp0cot_electricity.py" %*
