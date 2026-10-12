@echo off
setlocal
title K.E.V.I.N. Pressure Sensor Demo

cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python or check your PATH.
  echo You can also start the script from your existing VS Code terminal.
  pause
  exit /b 1
)

echo ========================================================
echo    K.E.V.I.N. - Pressure Sensor Demonstration
echo ========================================================
echo.
echo Finding the SAMD21 SensorHub automatically...
echo The dashboard will open in your default web browser.
echo.
echo When finished, click "Stop dashboard" in the webpage.
echo This window will then close by itself.
echo.
python tools\pressure_presentation_ui.py --serial-port auto --open-browser
if errorlevel 1 (
  echo.
  echo Could not start the live demonstration.
  echo Check that the SAMD21 is connected via USB and the old
  echo dashboard / PlatformIO Serial Monitor has been closed.
  echo.
  echo Or double-click Start_K.E.V.I.N._Simulated_Demo.cmd to rehearse.
  pause
  exit /b 1
)
endlocal
