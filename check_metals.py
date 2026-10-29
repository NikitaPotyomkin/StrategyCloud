"""Проверка готовности золота и серебра: метаданные, история, экономика.

Запуск:  python.exe check_metals.py

Метаданные — не для красоты: бэктест считает деньги как
    profit_rub = (diff / tick_size) * tick_value * lot
поэтому при tick_size = 0 деление невозможно, а при tick_value = 0 любая
прибыль превращается в ноль и все гейты по score обнуляются. Скрипт печатает
именно те поля, которые приходят в Python, и деньги на ходу цены для 0.01 лота.

История читается через copy_rates_from_pos: copy_rates_range(sym, ..., 2010)
возвращает пусто (упирается в «Max bars in chart»), это не показатель.
Боевой пайплайн вообще строит H1 из M5 за 90 дней (data_loader.load_h1).
"""

from datetime import datetime

import MetaTrader5 as mt5

SYMS = ("EURUSDrfd", "XAUUSDrfd", "XAGUSDrfd")   # EURUSD — эталон, он работает
GRIDS = {"XAUUSDrfd": (1200, 3600), "XAGUSDrfd": (2000, 5000)}
DEEP = 100000       # сколько баров просить; терминал отдаст сколько есть


def depth(sym, timeframe, label):
    """(кол-во баров, дата первого бара) — сколько реально отдаёт терминал."""
    rates = mt5.copy_rates_from_pos(sym, timeframe, 0, DEEP)
    if rates is None or len(rates) == 0:
        return 0, None
    return len(rates), datetime.utcfromtimestamp(int(rates[0]["time"]))


def money(pts, si, tick_value, tick_size, lot=0.01):
    """Сколько денег (в валюте счёта) стоит ход цены в pts пунктов на lot лотов."""
    if tick_size <= 0:
        return None
    return (pts * si.point / tick_size) * tick_value * lot


def main():
    if not mt5.initialize():
        print(f"MT5 initialize failed: {mt5.last_error()}")
        return 2
    try:
        acc = mt5.account_info()
        term = mt5.terminal_info()
        print(f"терминал: {getattr(term, 'name', '?')} | счёт: "
              f"{getattr(acc, 'login', '?')} {getattr(acc, 'currency', '?')}")

        for sym in SYMS:
            si = mt5.symbol_info(sym)
            print(f"\n=== {sym} ===")
            if si is None:
                print("  НЕ НАЙДЕН в терминале")
                continue
            tv = float(getattr(si, "trade_tick_value", 0) or 0)
            ts = float(getattr(si, "trade_tick_size", 0) or 0)
            n_h1, first_h1 = depth(sym, mt5.TIMEFRAME_H1, "H1")
            n_m5, first_m5 = depth(sym, mt5.TIMEFRAME_M5, "M5")
            print(f"  {si.description}")
            print(f"  point={si.point}  digits={si.digits}  "
                  f"contract={getattr(si, 'trade_contract_size', None)}  "
                  f"min_lot={si.volume_min}  step={si.volume_step}")
            print(f"  trade_tick_value={tv}  trade_tick_size={ts}")
            print(f"  spread={si.spread} pt  stops_level={si.trade_stops_level} pt  "
                  f"freeze={si.trade_freeze_level} pt")
            print(f"  swap long={si.swap_long} short={si.swap_short} "
                  f"mode={si.swap_mode} (0=points)")
            print(f"  H1: баров {n_h1}, первый {first_h1}")
            print(f"  M5: баров {n_m5}, первый {first_m5}  "
                  f"(пайплайн строит H1 из M5 за 90 дней)")

            m100 = money(100, si, tv, ts)
            if m100 is None:
                print("  !! tick_size = 0 -> profit_rub делить не на что, "
                      "бэктест вернёт нули/ошибку")
            else:
                print(f"  100 пунктов хода на 0.01 лота = {m100:,.2f} (валюта счёта)")

            for pts in GRIDS.get(sym, ()):
                m = money(pts, si, tv, ts)
                spread_m = money(si.spread, si, tv, ts)
                if m is not None and spread_m is not None:
                    print(f"  SL {pts} pt на 0.01 лота = {m:,.2f}; "
                          f"спред съедает {spread_m:,.2f} "
                          f"({pts / max(si.spread, 1):.1f} спредов на SL)")
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
