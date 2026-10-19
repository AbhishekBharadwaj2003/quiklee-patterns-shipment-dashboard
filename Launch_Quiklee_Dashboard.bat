@echo off
setlocal
cd /d "%~dp0"
title Quiklee Patterns Dashboard
if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  python -m venv .venv
  if errorlevel 1 goto error
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto error
python -m streamlit run dashboard.py
if errorlevel 1 goto error
endlocal
exit /b 0
:error
echo.
echo Dashboard failed to start. Check Python installation and the error above.
pause
endlocal
