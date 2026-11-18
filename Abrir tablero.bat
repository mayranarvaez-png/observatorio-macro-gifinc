@echo off
title Observatorio Macro-Financiero de Colombia
cd /d "%~dp0"

set "PY=python"
where python >nul 2>nul || set "PY=%USERPROFILE%\miniconda3\python.exe"

echo ================================================
echo   Observatorio Macro-Financiero de Colombia
echo ================================================
echo.
echo El tablero se abrira en tu navegador en unos segundos.
echo Para cerrarlo, cierra esta ventana.
echo.

"%PY%" -m streamlit run app.py --server.headless false --browser.gatherUsageStats false
pause
