@echo off
setlocal EnableExtensions
rem Register the auto-deploy task in GIT mode (deploy_pull.py default mode).
rem Every 60 minutes: git fetch -> git reset --hard origin/main -> py_compile gate -> restart bot.
rem Want it more often? change /MO 60 to /MO 5 (minutes) and run again.
rem Bot itself is started by you, this task does not create any autostart.
rem Run as administrator, one time.
set "PROJ=C:\Users\nikit\PycharmProjects\StrategyCloud"
if not exist "%PROJ%\deploy_pull.py" goto nopy
if not exist "%PROJ%\.venv\Scripts\python.exe" goto nopy

echo Registering "StrategyCloud deploy" (git mode, every 60 min) ...
schtasks /Create /SC MINUTE /MO 60 /TN "StrategyCloud deploy" /TR "cmd /c cd /d %PROJ% && .venv\Scripts\python.exe deploy_pull.py" /RL HIGHEST /F >nul 2>&1
if not errorlevel 1 goto ok
echo [WARN] highest privileges refused - retry with normal rights
schtasks /Create /SC MINUTE /MO 60 /TN "StrategyCloud deploy" /TR "cmd /c cd /d %PROJ% && .venv\Scripts\python.exe deploy_pull.py" /F
if errorlevel 1 goto fail
:ok
echo [OK] task "StrategyCloud deploy" registered: git mode, every 60 minutes.
echo Run it on demand (does not wait for the schedule):
echo    schtasks /Run /TN "StrategyCloud deploy"
echo Log:
echo    type "%PROJ%\journals\deploy.log"
goto end

:nopy
echo [ERROR] not found: %PROJ%\deploy_pull.py or %PROJ%\.venv\Scripts\python.exe
goto fail
:fail
pause
exit /b 1
:end
pause
endlocal
exit /b 0
