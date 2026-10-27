@echo off
REM ============================================================
REM  "Кнопка Pull": отправить код на боевую и сразу её обновить.
REM  Запускается НА ТЕСТОВОЙ машине (двойной клик или из PyCharm).
REM
REM  Что делает:
REM    1) git add -A / commit / push  — код уезжает в общий репозиторий
REM    2) schtasks /Run — дёргает на боевой машине задачу "StrategyCloud deploy",
REM       которая делает pull -> py_compile -> рестарт main.py
REM
REM  Один раз настроить:
REM    - на боевой: задача в планировщике "StrategyCloud deploy" (см. deploy_pull.py)
REM    - здесь: cmdkey /add:192.168.0.106 /user:nikit /pass:****
REM      (чтобы schtasks ходил на боевую без запроса пароля)
REM ============================================================

setlocal
set PROJECT=%~dp0
set TRADE_HOST=192.168.0.106
set TASK_NAME=StrategyCloud deploy

cd /d "%PROJECT%"

echo [1/3] Коммит...
git add -A
git commit -m "deploy %DATE% %TIME%" || echo    (нечего коммитить - продолжаю)

echo [2/3] Push...
git push origin main || goto :fail

echo [3/3] Запуск деплоя на боевой (%TRADE_HOST%)...
schtasks /S %TRADE_HOST% /Run /TN "%TASK_NAME%" || goto :fail

echo.
echo Готово. Статус смотри на боевой: journals\deploy.log и checkpoints\deploy_status.json
goto :end

:fail
echo.
echo ОШИБКА. Проверь сеть, доступ к шаре и задачу "%TASK_NAME%" на боевой машине.
exit /b 1

:end
endlocal
