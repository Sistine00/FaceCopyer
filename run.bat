@echo off
setlocal
title FaceCopyer Launcher
cd /d "%~dp0"

rem ---------------------------------------------------------------------------
rem  This launcher is path independent: it works no matter where the project is
rem  copied to. All machine specific settings live in facecopyer.ini (see
rem  setup.bat). The Python entry point does the real work.
rem ---------------------------------------------------------------------------

set "PY_EXE="
if exist "venv\Scripts\python.exe" set "PY_EXE=venv\Scripts\python.exe"
if not defined PY_EXE if exist ".venv\Scripts\python.exe" set "PY_EXE=.venv\Scripts\python.exe"

if defined PY_EXE goto launch

where py >nul 2>nul
if not errorlevel 1 set "PY_EXE=py -3"
if defined PY_EXE goto launch

where python >nul 2>nul
if not errorlevel 1 set "PY_EXE=python"
if defined PY_EXE goto launch

echo ============================================
echo  [ERROR] No Python interpreter found
echo.
echo  FaceCopyer needs Python 3.10 or newer.
echo    1. install it from https://www.python.org/downloads/
echo    2. run setup.bat once to finish the configuration
echo ============================================
echo.
pause
exit /b 1

:launch
%PY_EXE% "_facecopyer_launcher.py" %*
set "EXITCODE=%ERRORLEVEL%"

if defined FACECOPYER_QUIET exit /b %EXITCODE%

echo.
echo [DONE] FaceCopyer exited with code %EXITCODE%. Press any key to close.
pause >nul
exit /b %EXITCODE%
