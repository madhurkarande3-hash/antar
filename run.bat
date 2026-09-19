@echo off
REM ANTAR - one double-click to set up and run the backend on http://127.0.0.1:8000
cd /d "%~dp0backend"
where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)
if not exist .venv (
  echo Creating virtual environment...
  %PY% -m venv .venv || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements-dev.txt || (pause & exit /b 1)
)
start "" http://127.0.0.1:8000
.venv\Scripts\python.exe -m uvicorn antar.api:app --reload --port 8000
pause
