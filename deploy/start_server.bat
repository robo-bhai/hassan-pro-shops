@echo off
cd /d "%~dp0\.."
call venv\Scripts\activate
python deploy\run_server.py
pause
