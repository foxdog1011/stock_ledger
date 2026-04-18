@echo off
REM JARVIS Watchdog — auto-start local API and monitor video pipeline.
REM Place a shortcut to this file in shell:startup to run on boot.

cd /d "%~dp0\.."

REM Load .env
for /f "usebackq tokens=1,2 delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
)

if not exist logs mkdir logs
echo [watchdog] Starting at %date% %time% >> logs\watchdog.log

python scripts\watchdog.py >> logs\watchdog.log 2>&1
