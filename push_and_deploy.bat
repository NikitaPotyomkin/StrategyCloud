@echo off
REM ============================================================
REM  "Pull button": send code to the production box and update it.
REM  Run on the TEST machine (double click or from PyCharm).
REM
REM  What it does:
REM    1) git add -A / commit / push - code goes to the shared repo
REM    2) schtasks /Run - triggers "StrategyCloud deploy" on production,
REM       which does pull -> py_compile -> restart main.py
REM
REM  KEEP THIS FILE ASCII-ONLY. cmd.exe reads .bat byte by byte and UTF-8
REM  Cyrillic breaks line parsing: it starts running word fragments like
REM  "'puwena' is not recognized". English text here is not laziness.
REM
REM  One-time setup:
REM    - on production: scheduled task "StrategyCloud deploy" (deploy_pull.py)
REM    - here: cmdkey /add:192.168.0.106 /user:nikit /pass:****
REM ============================================================

setlocal
set PROJECT=%~dp0
set TRADE_HOST=192.168.0.106
set TASK_NAME=StrategyCloud deploy

cd /d "%PROJECT%"

echo [1/3] Commit...
git add -A
git commit -m "deploy %DATE% %TIME%" || echo    nothing to commit - continue

echo [2/3] Push...
git push origin main || goto :fail

echo [3/3] Trigger deploy on production (%TRADE_HOST%)...
REM Non-critical step: the commit is already in origin/main and production
REM picks it up on its scheduled tick (the task pulls git once an hour).
REM A failure here means only "could not trigger now", not "deploy failed".
schtasks /S %TRADE_HOST% /Run /TN "%TASK_NAME%" >nul 2>&1
if errorlevel 1 (
    echo       could not trigger the task - waiting for the scheduled tick
    echo       check: dashboard, deploy badge
) else (
    echo       task triggered
)

echo.
echo Done. Status on production: journals\deploy.log and journals\deploy_status.json
goto :end

:fail
echo.
echo ERROR. Check network, share access and task "%TASK_NAME%" on production.
exit /b 1

:end
endlocal
