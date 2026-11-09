@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo [Pet Hospital Backend]
echo   URL=http://127.0.0.1:8080/
echo Keep this window open. Press Ctrl+C to stop.
echo.

pethospital.exe
echo.
echo [exited] code=%ERRORLEVEL%
pause
endlocal
