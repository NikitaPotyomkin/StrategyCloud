"""Пилот: сравнение двух моделей бэктеста на одних и тех же сигналах.

В проекте живут две модели исполнения:

  * legacy-петля (своя в каждом из ~166 файлов стратегий):
      вход по close[i] сигнального бара, спред не вычитается вообще,
      незакрытая за 49 баров сделка молча выбрасывается из выборки,
      P&L = (цена_выхода - цена_входа) * лот * tick_value;
  * _bt_core.run_backtest:
      вход по open[i+1] + спред, выход со спредом, таймаута нет,
      P&L = (дельта / tick_size) * tick_value * лот.

Обе модели гоняются на ОДНОМ ряду с ОДНИМИ предикатами входа/выхода и одними
SL/TP. Это замер, а не правка: инструмент ничего не меняет на диске.

Что смотреть:
  * колонка core/legacy по profit — во сколько раз расходятся деньги;
  * колонка n (сделок) — сколько сделок legacy-модель потеряла на таймауте;
  * --units — проверка масштаба: сколько денег даёт один и тот же стоп по
    каждой формуле. Расхождение должно равняться 1/tick_size.

Запуск:
    python tools/loop_model_pilot.py                    # семейство mom_
    python tools/loop_model_pilot.py --family osc_ --limit 3
    python tools/loop_model_pilot.py --key reg_ridge    # контроль: одна модель
    python tools/loop_model_pilot.py --units            # только проверка единиц
"""
import argparse
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

SIM_LOT = 0.01


def _grid(spec):
    """(min, max, step) -> [min, ..., max] как в реестре."""
    lo, hi, step = spec
    out = []
    value = lo
    while value <= hi + 1e-9:
        out.append(int(round(value)))
        value += step
    return out


def _mid(values):
    return values[len(values) // 2]


def _fmt(value):
    return f"{value:,.2f}" if isinstance(value, float) else f"{value:,}"


def units_report(mt5, config, symbols):
    """Масштаб P&L: одна и та же дистанция стопа по двум формулам."""
    print("\n═══ ПРОВЕРКА ЕДИНИЦ ═══")
    print(f"{'символ':<12} {'tick_size':>11} {'tick_value':>11} "
          f"{'legacy $':>12} {'core $':>12} {'core/legacy':>12}")
    print("─" * 76)
    for symbol in symbols:
        info = mt5.symbol_info(symbol)
        if info is None:
            print(f"{symbol:<12} нет в терминале")
            continue
        point = info.point
        tick_value = info.trade_tick_value
        tick_size = info.trade_tick_size or point
        sl_pts = _mid(_grid(config.SL_POINTS_GRID[symbol]))
        diff = sl_pts * point
        legacy = diff * SIM_LOT * tick_value
        core = (diff / tick_size) * tick_value * SIM_LOT
        ratio = core / legacy if legacy else float('nan')
        print(f"{symbol:<12} {tick_size:>11.6f} {tick_value:>11.4f} "
              f"{legacy:>12.6f} {core:>12.4f} {ratio:>12,.0f}")
    print("\nЕсли core/legacy = 1/tick_size, то формулы расходятся в единицах,")
    print("и profit/mdd/recovery/score между семействами несравнимы.")
    print("Отношения (PF, win_rate, sharpe) от масштаба не зависят.")


def run_key(mt5, config, key, record, symbol, df, sl, tp):
    """Прогнать одну пару (ключ, символ) двумя моделями."""
    module_name = 'strategies.' + record['module']
    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:                      # noqa: BLE001 — отчёт, не падение
        return None, f"импорт {module_name}: {exc!r}"

    calc = getattr(mod, record['calc'], None)
    legacy_fn = getattr(mod, 'backtest', None)
    entry_fn = getattr(mod, record.get('entry', 'check_entry'), None)
    exit_fn = getattr(mod, record.get('exit', 'check_exit'), None)
    if calc is None or legacy_fn is None or entry_fn is None or exit_fn is None:
        return None, "нет calc/backtest/entry/exit"

    info = mt5.symbol_info(symbol)
    if info is None:
        return None, "символ не найден"
    point, tick_value = info.point, info.trade_tick_value
    tick_size, spread = info.trade_tick_size or info.point, info.spread

    param_key = _mid(record.get('grid') or [1])
    row = {'key': key, 'symbol': symbol, 'param': param_key, 'error': ''}

    try:
        from strategies._bt_core import run_backtest
        p_core, n_core, _ = run_backtest(
            df, calc, entry_fn, exit_fn, param_key, sl, tp,
            point, tick_value, tick_size, SIM_LOT, spread)
        row['core_profit'], row['core_n'] = float(p_core), int(n_core)
    except Exception as exc:                      # noqa: BLE001
        row['error'] += f"core: {exc!r} "

    try:
        p_leg, n_leg, _ = legacy_fn(
            df, param_key, sl, tp, point, tick_value, tick_size,
            sim_lot=SIM_LOT, spread_points=spread)
        row['leg_profit'], row['leg_n'] = float(p_leg), int(n_leg)
    except TypeError:
        # Часть модулей не принимает spread_points — это и есть legacy-модель.
        p_leg, n_leg, _ = legacy_fn(df, param_key, sl, tp, point,
                                    tick_value, tick_size, SIM_LOT)
        row['leg_profit'], row['leg_n'] = float(p_leg), int(n_leg)
    except Exception as exc:                      # noqa: BLE001
        row['error'] += f"legacy: {exc!r} "

    return row, ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family', default='mom_',
                        help='префикс имени модуля (по умолчанию mom_)')
    parser.add_argument('--key', action='append', default=None,
                        help='конкретный ключ реестра (можно несколько раз)')
    parser.add_argument('--symbol', action='append', default=None,
                        help='конкретный символ (можно несколько раз)')
    parser.add_argument('--limit', type=int, default=0,
                        help='ограничить число ключей и символов')
    parser.add_argument('--sl', type=int, default=0,
                        help='SL в пунктах (по умолчанию середина сетки символа)')
    parser.add_argument('--tp', type=int, default=0,
                        help='TP в пунктах (по умолчанию 2*SL)')
    parser.add_argument('--units', action='store_true',
                        help='только проверка единиц P&L, без прогонов')
    args = parser.parse_args()

    import MetaTrader5 as mt5
    import config
    from data_loader import load_h1
    from strategies import _registry as reg

    if not mt5.initialize():
        raise SystemExit(f"MT5 не инициализирован: {mt5.last_error()}")

    try:
        symbols = list(args.symbol or config.SYMBOLS)
        if args.limit:
            symbols = symbols[:args.limit]

        if args.units:
            units_report(mt5, config, symbols)
            return

        if args.key:
            keys = [k for k in args.key if k in reg.REGISTRY]
            missing = [k for k in args.key if k not in reg.REGISTRY]
            if missing:
                print(f"нет в реестре: {', '.join(missing)}")
        else:
            keys = [k for k, r in reg.REGISTRY.items()
                    if str(r.get('module', '')).startswith(args.family)]
            keys.sort()
            if args.limit:
                keys = keys[:args.limit]

        if not keys:
            raise SystemExit(f"ключей с префиксом {args.family!r} нет в реестре")

        print(f"Ключей: {len(keys)}; символов: {len(symbols)}; "
              f"sim_lot={SIM_LOT}")
        print("legacy = своя петля модуля, core = strategies/_bt_core.run_backtest\n")

        rows = []
        for symbol in symbols:
            df = load_h1(symbol)
            if df is None or len(df) < 200:
                print(f"{symbol}: нет данных, пропуск")
                continue
            sl = args.sl or _mid(_grid(config.SL_POINTS_GRID[symbol]))
            tp = args.tp or sl * 2
            for key in keys:
                row, err = run_key(mt5, config, key, reg.REGISTRY[key],
                                   symbol, df, sl, tp)
                if row is None:
                    print(f"  {key} @ {symbol}: {err}")
                    continue
                row['sl'], row['tp'] = sl, tp
                rows.append(row)

        if not rows:
            raise SystemExit("нечего показывать: все прогоны упали")

        print(f"\n{'ключ':<22} {'символ':<11} {'SL/TP':>11} "
              f"{'legacy':>12} {'core':>12} {'n_leg':>6} {'n_core':>6} {'core/leg':>9}")
        print("─" * 96)
        for row in rows:
            leg = row.get('leg_profit', 0.0)
            core = row.get('core_profit', 0.0)
            ratio = (core / leg) if leg else float('nan')
            print(f"{row['key']:<22} {row['symbol']:<11} "
                  f"{row['sl']:>5}/{row['tp']:<5} "
                  f"{leg:>12,.4f} {core:>12,.2f} "
                  f"{row.get('leg_n', 0):>6} {row.get('core_n', 0):>6} "
                  f"{ratio:>9,.0f}"
                  + (f"  {row['error']}" if row['error'] else ""))

        n_leg = sum(r.get('leg_n', 0) for r in rows)
        n_core = sum(r.get('core_n', 0) for r in rows)
        lost = n_core - n_leg
        print("─" * 96)
        print(f"Сделок: legacy {n_leg}, core {n_core} (разница {lost:+d})")
        print("\nКак читать: core/leg — расхождение денег (ожидаемо 1/tick_size),")
        print("разница в сделках — потери legacy-модели на 50-барном таймауте.")
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
