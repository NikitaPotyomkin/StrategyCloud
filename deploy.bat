@echo off
setlocal EnableExtensions
REM ============================================================
REM  deploy.bat - restart the bot with the current code (LOCAL machine).
REM
REM  The bot runs on THIS machine, from THIS folder:
REM    <this folder>\.venv\Scripts\python.exe main.py
REM  It trades through the local MetaTrader 5 terminal, so no file copy,
REM  no share and no ssh is needed: edit files here, run this bat.
REM
REM  What it does (via restart_bot.py):
REM    1) py_compile of all production .py files - broken code is NOT started;
REM    2) stop the running main.py (if any) - two bots must never trade at once;
REM    3) start main.py in its own console window.
REM
REM  All messages are ASCII on purpose: cmd.exe parses batch files byte-wise
REM  and breaks on Cyrillic text with chcp 65001.
REM ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto nopy

echo.
echo [1/2] py_compile gate + restart ...
".venv\Scripts\python.exe" restart_bot.py
if errorlevel 1 goto fail

echo.
echo [OK] bot restarted with the current code.
echo      Check the new bot console for:
echo        Chekpoints path and journals\run.log
REM  (there is no checkpoint cache right now -> the bot starts a FULL recalculation,
REM   which takes 2.5-4 hours and runs synchronously: the trading loop waits for it)
echo      and journals\run.log
goto end

:nopy
echo.
echo [ERROR] .venv\Scripts\python.exe not found in "%~dp0"
echo         Run deploy.bat from the project folder, or fix the venv path.
goto fail

:fail
echo.
echo [ERROR] restart failed (see messages above). The bot was NOT restarted.
pause
exit /b 1

:end
pause
endlocal
exit /b 0
