@echo off
setlocal EnableExtensions
REM ============================================================
REM  setup_on_store.bat - FIRST-TIME setup of the bot on the 24/7 machine.
REM  Run this ON THE MACHINE THAT WILL KEEP THE BOT (the "store" PC),
REM  from the project folder, after the code was copied there.
REM
REM  It does NOT copy code and does NOT start the bot. It only prepares
REM  the Python environment:
REM    1) python -m venv .venv      (isolated env, no system packages)
REM    2) pip install -r requirements.txt
REM
REM  Requirements before running:
REM    - Python 3.11+ installed and "py" or "python" available in PATH;
REM    - MetaTrader 5 terminal installed and LOGGED IN to the trading account,
REM      with Algo Trading enabled - the MetaTrader5 python package talks ONLY
REM      to a terminal running on the same machine.
REM
REM  After this script: run deploy.bat (py_compile gate + start main.py).
REM
REM  All messages are ASCII on purpose (cmd parses batch files byte-wise).
REM ============================================================
cd /d "%~dp0"

echo.
echo [1/3] checking python ...
where py >nul 2>&1
if not errorlevel 1 goto have_py
where python >nul 2>&1
if not errorlevel 1 goto have_python
echo [ERROR] Neither "py" nor "python" found in PATH.
echo         Install Python 3.11+ and enable "Add python.exe to PATH".
goto fail

:have_py
set "PYEXE=py -3"
goto make_venv

:have_python
set "PYEXE=python"

:make_venv
if exist ".venv\Scripts\python.exe" goto have_venv
echo [2/3] creating .venv ...
%PYEXE% -m venv .venv
if errorlevel 1 goto venvfail
goto install

:have_venv
echo [2/3] .venv already exists - reusing it

:install
echo [3/3] installing requirements ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto pipfail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pipfail

echo.
echo [OK] environment is ready: .venv\Scripts\python.exe
echo      Next steps:
echo        1) make sure MetaTrader 5 is running and logged in (Algo Trading ON)
echo        2) run deploy.bat  -> py_compile gate + start main.py
echo        3) add a scheduled task "run at logon" for nikit (not SYSTEM!)
goto end

:venvfail
echo.
echo [ERROR] failed to create .venv
goto fail

:pipfail
echo.
echo [ERROR] pip install failed - check internet access and requirements.txt
goto fail

:fail
pause
exit /b 1

:end
pause
endlocal
exit /b 0
