"""Фоновый (async) ПОЛНЫЙ пересчёт стратегий.

Зачем этот модуль
-----------------
run_full_backtest — синхронный вызов: полный проход 49–77 тыс. комбинаций занимает
150–230 мин, и всё это время боевой цикл закрыт — бары не опрашиваются, сигналы не
рождаются, трейлинг и аварийные защиты (daily loss, equity stop, margin) не
срабатывают, а открытые позиции живут только на брокерских SL/TP.

Здесь та же работа уходит в отдельный поток: цикл продолжает торговать, а результат
применяется, когда job завершился (main.py: _bg_poll → вход в ночной блок в лайт-режиме).

Почему поток, а не отдельный процесс
------------------------------------
- тяжёлая часть и так считается в mp.Pool внутри run_full_backtest, поэтому лишняя
  сериализация данных между процессами не нужна;
- поток почти всё время ждёт pool.imap_unordered, GIL не держит;
- не нужно маршалить symbol_data и чекпойнты.

Что job отдаёт наружу
---------------------
Практически ничего, кроме факта успеха. Его полезный результат — свежие чекпойнты
(их пишет сам run_full_backtest). Поэтому применение сводится к обычному входу в
ночной блок в лайт-режиме: считать нечего, результат берётся из чекпойнтов. Так
применение остаётся ровно тем же кодом, что и при синхронном прогоне.

Инварианты
----------
- расчёт идёт по СНИМКУ данных на момент старта (df_h1.copy()): боевой цикл продолжает
  дописывать закрытые H1-бары в symbol_data, а job обязан видеть неизменяемую картину;
- одновременно живёт не более одного job (см. main.py: _bg_running/_bg_start);
- бэктест НЕ обращается к терминалу (все mt5-вызовы functions.py живут около строк
  565–604, вне run_full_backtest), поэтому фоновый поток не конкурирует с боевым
  циклом за API MT5;
- при рестарте main.py job умирает вместе с процессом. Чекпойнты могут остаться
  частично обновлёнными — это безопасно: следующий полный проход их перезапишет,
  а результат в торговлю попадёт только после успешного завершения job.
"""

import threading
import time


def snapshot_symbol_data(symbol_data):
    """Снимок рыночных данных для фонового расчёта.

    Главный цикл продолжает обновлять df_h1 (закрытые H1-бары), поэтому job обязан
    считать по неизменяемой копии — иначе это гонка на объекте pandas. Копия неглубокая:
    append/вытеснение баров создаёт НОВЫЙ объект DataFrame, старые блоки не меняются.
    """
    snap = {}
    for sym, sd in (symbol_data or {}).items():
        if not isinstance(sd, dict):
            continue
        nd = dict(sd)
        df = sd.get('df_h1')
        if df is not None:
            try:
                nd['df_h1'] = df.copy(deep=False)
            except Exception:
                pass  # снимок без df_h1: символ просто не попадёт в расчёт
        snap[sym] = nd
    return snap


class BacktestJob:
    """Один фоновый ПОЛНЫЙ пересчёт. Боевой цикл не блокирует."""

    def __init__(self, symbols, symbol_data, strategy_params, backtest_config,
                 test_strategy=None, test_mode=False, force_recalc=True,
                 is_night_run=True):
        self._args = (list(symbols), snapshot_symbol_data(symbol_data),
                      strategy_params, backtest_config)
        self._kwargs = dict(test_strategy=test_strategy, test_mode=test_mode,
                            force_recalc=force_recalc, is_night_run=is_night_run)
        self._done = threading.Event()
        self._result = None
        self._error = None
        self._t0 = None
        self._t1 = None
        self._thread = threading.Thread(target=self._run, name='backtest-job', daemon=True)

    # ── запуск и тело потока ──
    def start(self):
        self._t0 = time.time()
        self._thread.start()
        return self

    def _run(self):
        try:
            # Локальный импорт: functions уже импортирован main.py, а модульный импорт
            # здесь создал бы цикл «main → backtest_job → functions → main».
            from functions import run_full_backtest
            self._result = run_full_backtest(*self._args, **self._kwargs)
        except Exception as exc:
            self._error = repr(exc)
        finally:
            self._t1 = time.time()
            self._done.set()

    # ── состояние ──
    def running(self):
        return not self._done.is_set()

    def poll(self):
        return self._done.is_set()

    def ok(self):
        return self._done.is_set() and self._error is None

    def error(self):
        return self._error

    def result(self):
        """(top_results, all_results) или None. Нужен только для диагностики:
        применяются не эти объекты, а свежие чекпойнты, которые job уже записал."""
        return self._result

    def elapsed_min(self):
        t0 = self._t0
        if not t0:
            return 0.0
        t1 = self._t1 if self._t1 else time.time()
        return (t1 - t0) / 60.0
