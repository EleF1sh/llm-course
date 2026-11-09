@echo off
setlocal EnableExtensions

set "OFFICE=%~dp0"
if "%OFFICE:~-1%"=="\" set "OFFICE=%OFFICE:~0,-1%"
for %%I in ("%OFFICE%\..\xAgent") do set "XAGENT=%%~fI"

cd /d "%OFFICE%"
if errorlevel 1 (
  echo [ERROR] cannot cd to: %OFFICE%
  pause
  exit /b 1
)

if not exist "%XAGENT%\run.py" (
  echo [ERROR] run.py not found:
  echo   %XAGENT%\run.py
  pause
  exit /b 1
)

set "PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

echo OFFICE=%OFFICE%
echo XAGENT=%XAGENT%
echo PY=%PY%
echo.
echo Starting xAgent ...
echo.

"%PY%" "%XAGENT%\run.py"
set "EC=%ERRORLEVEL%"
echo.
echo [xAgent exited] code=%EC%
pause
endlocal