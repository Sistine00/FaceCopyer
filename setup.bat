@echo off
setlocal
title FaceCopyer Setup
cd /d "%~dp0"

rem  Deployment wizard: writes / updates facecopyer.ini (paths, ports, device,
rem  cache policy, download source). Reuse run.bat so the Python discovery logic
rem  is only maintained in one place.

set "FACECOPYER_QUIET=1"
call "%~dp0run.bat" --setup
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
  echo [DONE] Configuration saved. Double click run.bat to start FaceCopyer.
) else (
  echo [ERROR] Setup failed with code %EXITCODE%.
)
echo.
pause >nul
exit /b %EXITCODE%
