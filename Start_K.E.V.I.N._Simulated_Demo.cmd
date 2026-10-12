@echo off
setlocal
title K.E.V.I.N. SIMULATED Demo

cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found in PATH.
  pause
  exit /b 1
)

echo =========================================================
echo    SIMULATED DEMO - NOT CONNECTED TO A REAL SENSOR
echo =========================================================
echo.
echo A clearly labeled simulation will open in the browser.
echo When finished, click "Stop dashboard" to exit.
echo.
python tools\pressure_presentation_ui.py --demo --open-browser
if errorlevel 1 (
  echo Could not start the simulated demo. Check Python dependencies.
  pause
  exit /b 1
)
endlocal
