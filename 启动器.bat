@echo off
setlocal
cd /d "%~dp0"

set PYEXE=%~dp0python\python.exe

if not exist "%PYEXE%" (
  echo ============================================================
  echo   ERROR: Python runtime not found at
  echo     %PYEXE%
  echo   Please keep the "python" folder next to this file.
  echo ============================================================
  pause
  exit /b 1
)

echo ============================================================
echo   FAERS Pharmacovigilance Toolbox - Launcher
echo   Starting... the browser will open automatically.
echo   Address: http://localhost:8500
echo   Keep this window open while using the toolbox.
echo ============================================================
echo.

"%PYEXE%" -m streamlit run launcher.py --server.port 8500 --browser.gatherUsageStats false

echo.
echo Launcher closed. Press any key to exit.
pause
