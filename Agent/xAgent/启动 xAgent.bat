@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "HERE=%CD%"

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] python not found. Install Python and add it to PATH.
  pause
  exit /b 1
)

where wt >nul 2>&1
if not errorlevel 1 (
  wt -d "%HERE%" -- python run.py
  if not errorlevel 1 exit /b 0
  echo [WARN] Windows Terminal failed, falling back to this window...
)

python run.py
if errorlevel 1 (
  echo.
  echo [ERROR] exit code %ERRORLEVEL%
  pause
)
endlocal