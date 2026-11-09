@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

rem 覆盖 .env 端口，与 office/.mcp.json 中的 8091 一致
set "MCP_HOST=127.0.0.1"
set "MCP_PORT=8091"
set "PYTHONPATH=%~dp0src"

echo.
echo [AnythingLLM MCP]
echo   PYTHON=%PY%
echo   URL=http://127.0.0.1:8091/mcp
echo   Need AnythingLLM Desktop running on http://127.0.0.1:3001
echo Keep this window open. Press Ctrl+C to stop.
echo.

"%PY%" -m anythingllm_mcp
echo.
echo [exited] code=%ERRORLEVEL%
pause
endlocal
