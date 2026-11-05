@echo off
rem Run once, by double-clicking, on the customer's Windows PC. Needs Python 3.10+ (python.org, tick "Add to PATH").
cd /d "%~dp0\.."
where py >nul 2>nul || (echo Python is not installed. Install Python 3.12 from python.org first. & pause & exit /b 1)
if not exist venv py -3 -m venv venv
call venv\Scripts\activate
python -m pip install --upgrade pip
if exist wheelhouse (
  pip install --no-index --find-links wheelhouse -r requirements.txt
) else (
  pip install -r requirements.txt
)
if errorlevel 1 (echo Package install failed. & pause & exit /b 1)
python deploy\setup_install.py
echo.
echo Next: double-click deploy\start_server.bat
pause
