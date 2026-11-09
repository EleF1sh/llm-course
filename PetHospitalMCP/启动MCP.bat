@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

set "PYTHONPATH=%~dp0src"
set "MCP_HOST=127.0.0.1"
set "MCP_PORT=8090"
set "PET_HOSPITAL_BASE_URL=http://127.0.0.1:8080"

echo.
echo [PetHospital MCP]
echo   PYTHON=%PY%
echo   URL=http://127.0.0.1:8090/mcp
echo   Backend=%PET_HOSPITAL_BASE_URL%
echo.
echo Keep this window open. Press Ctrl+C to stop.
echo.

"%PY%" -m pet_hospital_mcp
echo.
echo [exited] code=%ERRORLEVEL%
pause
endlocal
