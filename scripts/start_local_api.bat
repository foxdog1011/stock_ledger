@echo off
REM Start local JARVIS stock-ledger API on port 8003.
REM Loads env vars from .env, uses local SQLite at local_ledger.db.
REM Usage: double-click this file OR run from terminal.

cd /d "%~dp0\.."
set DB_PATH=%CD%\local_ledger.db
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM Load .env into environment
for /f "usebackq tokens=1,2 delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
)

echo [start_local_api] Starting uvicorn on http://localhost:8003 ...
echo [start_local_api] Logs: %CD%\logs\local_api.log
if not exist logs mkdir logs

python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8003 --log-level warning >> logs\local_api.log 2>&1
