"""Пробный прогон ТОЛЬКО по металлам: бэктест + отчёт по семействам.

Запуск:  python.exe probe_metals.py
         python.exe probe_metals.py XAUUSDrfd      # только золото

Что делает:
  1) подкачивает M5-историю по символу (data_loader.load_h1 строит H1 из M5 за 90 дней);
  2) гоняет полный пересчёт комбинаций ровно по этим символам (BacktestJob в фоне,
     остальные символы и их чекпойнты не трогаются);
  3) печатает по семействам: лучший score, сколько комбинаций, сколько с плюсом,
     PF/WR/сделки/профит у лучшей комбинации и сколько комбинаций годны к плану
     (сделок >= 10 и PF >= 1.2 — уже ПОСЛЕ спреда, он в бэктесте моделируется).

Критерий «интересно»: хотя бы 3-5 семейств с best score >= min_score (1.0).
Ничего не пишет в баланс и не выставляет ордера — только расчёт.
"""

import sys
import time

import MetaTrader5 as mt5

import data_loader
import functions
from config import build_default_configs

METALS = ("XAUUSDrfd", "XAGUSDrfd")


def _warmup(symbol):
    """Просим терминал отдать M5-историю (иначе load_h1 вернёт пусто)."""
    try:
        mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 60000)
        mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 60000)
    except Exception:
        pass


def _get(row, *keys, default=None):
    for k in keys:
        if isinstance(row, dict) and row.get(k) is not None:
            return row[k]
    return default


def report(symbol, min_score):
    # load_checkpoint возвращает кортеж (results, last_bar_time, families).
    # Без распаковки в rows попадал сам кортеж — отсюда «комбинаций 3», family «?»
    # и нули во всех колонках отчёта.
    _ck = functions.load_checkpoint(symbol)
    if isinstance(_ck, tuple):
        rows = _ck[0] or []
    else:
        rows = _ck or []
    print(f"\n=== {symbol}: комбинаций {len(rows)} ===")
    if not rows:
        print("  чекпойнт пуст — расчёт ничего не выдал")
        return
    fams = {}
    for r in rows:
        fams.setdefault(_get(r, 'strategy_type', 'type', 'family', default='?'), []).append(r)

    table = []
    for fam, lst in fams.items():
        scored = [(float(_get(r, 'score', default=0.0) or 0.0), r) for r in lst]
        best_score, best_row = max(scored, key=lambda x: x[0])
        positive = sum(1 for s, _ in scored if s > 0)
        tradable = [r for r in lst
                    if (_get(r, 'n_trades', default=0) or 0) >= 10
                    and (_get(r, 'profit_factor', 'pf', default=0.0) or 0.0) >= 1.2]
        table.append((best_score, fam, len(lst), positive, len(tradable), best_row))
    table.sort(key=lambda x: x[0], reverse=True)

    head = (f"{'family':<20}{'best':>7}{'combos':>8}{'pos':>5}{'ok':>5}"
            f"{'n':>5}{'PF':>7}{'WR%':>7}{'profit':>10}  param_key")
    print(head)
    print("-" * len(head))
    for best_score, fam, n_all, positive, n_ok, row in table[:15]:
        print(f"{fam:<20}{best_score:>7.2f}{n_all:>8}{positive:>5}{n_ok:>5}"
              f"{(int(_get(row, 'n_trades', default=0) or 0)):>5}"
              f"{(float(_get(row, 'profit_factor', 'pf', default=0.0) or 0.0)):>7.2f}"
              f"{(float(_get(row, 'win_rate', default=0.0) or 0.0)):>7.1f}"
              f"{(float(_get(row, 'profit', default=0.0) or 0.0)):>10.0f}"
              f"  {_get(row, 'param_key', default='')}")

    above = sum(1 for t in table if t[0] >= min_score)
    ok_fams = sum(1 for t in table if t[4] > 0)
    print(f"\n  семейств с best score >= {min_score:.2f}: {above} из {len(table)}")
    print(f"  семейств хотя бы с одной годной комбинацией (n>=10, PF>=1.2): {ok_fams}")
    verdict = ("ИНТЕРЕСНО: есть кандидаты" if above >= 3
               else "СЛАБО: порог проходит меньше 3 семейств — в план не попадёт")
    print(f"  вердикт: {verdict}")


def main():
    symbols = tuple(sys.argv[1:]) or METALS
    if not mt5.initialize():
        print(f"MT5 initialize failed: {mt5.last_error()}")
        return 2
    try:
        acc = mt5.account_info()
        print(f"счёт {getattr(acc, 'login', '?')} {getattr(acc, 'currency', '?')}, "
              f"символы: {', '.join(symbols)}")

        app = build_default_configs()
        symbol_data = {}
        for sym in symbols:
            si = mt5.symbol_info(sym)
            if si is None:
                print(f"  {sym}: нет в терминале — пропуск")
                continue
            _warmup(sym)
            df = data_loader.load_h1(sym)
            if df is None or len(df) < 30:
                print(f"  {sym}: мало H1-данных ({0 if df is None else len(df)} баров) — пропуск")
                continue
            symbol_data[sym] = {'df_h1': df, 'info': si}
            print(f"  {sym}: H1 баров {len(df)}, спред {si.spread} pt, "
                  f"tick_value {si.trade_tick_value} tick_size {si.trade_tick_size}")
        if not symbol_data:
            print("нечего считать")
            return 1

        from backtest_job import BacktestJob
        job = BacktestJob(tuple(symbol_data), symbol_data, app.strategy_params,
                          app.backtest_config, force_recalc=True,
                          is_night_run=False).start()
        t0 = time.time()
        while job.running():
            time.sleep(15)
            print(f"  ... {time.time() - t0:.0f} с", flush=True)
        if not job.ok():
            print(f"ошибка расчёта: {job.error()}")
            return 1
        print(f"расчёт закончен за {job.elapsed_min():.1f} мин")

        min_score = float(getattr(app.risk_params, 'min_score', 1.0) or 1.0)
        for sym in symbol_data:
            report(sym, min_score)
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
