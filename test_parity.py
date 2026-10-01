# -*- coding: utf-8 -*-
"""Parity-тест рефакторинга check_active_signals (23 elif-ветки -> dispatch-таблица).

Запуск из папки StrategyCloud (в venv):
    python test_parity.py --golden   # снять эталон с ТЕКУЩЕГО check_active_signals
    python test_parity.py --check    # A/B новой реализации vs архив _obsolete_* + сверка с golden

После рефакторинга strategy_engine.py содержит архив прежней реализации под именем
_obsolete_check_active_signals (тело побайтово прежнее). --check прогоняет ОБЕ
реализации на одинаковых синтетических сценариях и построчно сравнивает лог
решений (ордера/закрытия/печать). Пустой diff = поведение идентично.

Тест НЕ торгует: mt5 подменяется фейком, send_order/close_order/_record_close —
заглушками, пишущими в лог событий.
"""
import argparse
import difflib
import io
import sys
import types
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime

import numpy as np
import pandas as pd

import strategy_engine as se
from config import RiskParams

NOW = datetime(2026, 9, 29, 19, 0, 0)

SYMBOLS = ['EURUSDrfd', 'GBPUSDrfd', 'USDJPYrfd', 'USDCHFrfd',
           'USDCADrfd', 'AUDUSDrfd', 'NZDUSDrfd']

TYPES = ['stoch', 'parabolic', 'ma', 'rf', 'logreg', 'macd_cross', 'rsi_rev',
         'bollinger', 'ema_cross', 'rsi_div', 'ichimoku', 'zscore', 'autocorr',
         'hurst', 'lrc', 'percentile', 'runs', 'coint', 'sharpe', 'skewness',
         'bayesian', 'kurtosis', 'chi_square']

CALC_ARG = {
    'stoch': 'calc_stochastic_fn', 'parabolic': 'calc_parabolic_fn',
    'ma': 'calc_moving_average_fn', 'rf': 'calc_random_forest_fn',
    'logreg': 'calc_logreg_fn', 'macd_cross': 'calc_macd_cross_fn',
    'rsi_rev': 'calc_rsi_reversal_fn', 'bollinger': 'calc_bollinger_fn',
    'ema_cross': 'calc_ema_crossover_fn', 'rsi_div': 'calc_rsi_divergence_fn',
    'ichimoku': 'calc_ichimoku_fn', 'zscore': 'calc_zscore_fn',
    'autocorr': 'calc_autocorrelation_fn', 'hurst': 'calc_hurst_fn',
    'lrc': 'calc_lr_channel_fn', 'percentile': 'calc_percentile_fn',
    'runs': 'calc_runs_test_fn', 'coint': 'calc_cointegration_fn',
    'sharpe': 'calc_rolling_sharpe_fn', 'skewness': 'calc_skewness_fn',
    'bayesian': 'calc_bayesian_trend_fn', 'kurtosis': 'calc_kurtosis_fn',
    'chi_square': 'calc_chi_square_fn',
}
ENTRY_ARG = {
    'stoch': 'check_entry_stoch_fn', 'parabolic': 'check_entry_parabolic_fn',
    'ma': 'check_entry_ma_fn', 'rf': 'check_entry_rf_fn',
    'logreg': 'check_entry_logreg_fn', 'macd_cross': 'check_entry_macd_cross_fn',
    'rsi_rev': 'check_entry_rsi_reversal_fn', 'bollinger': 'check_entry_bollinger_fn',
    'ema_cross': 'check_entry_ema_crossover_fn', 'rsi_div': 'check_entry_rsi_divergence_fn',
    'ichimoku': 'check_entry_ichimoku_fn', 'zscore': 'check_entry_zscore_fn',
    'autocorr': 'check_entry_autocorr_fn', 'hurst': 'check_entry_hurst_fn',
    'lrc': 'check_entry_lrc_fn', 'percentile': 'check_entry_percentile_fn',
    'runs': 'check_entry_runs_fn', 'coint': 'check_entry_coint_fn',
    'sharpe': 'check_entry_sharpe_fn', 'skewness': 'check_entry_skewness_fn',
    'bayesian': 'check_entry_bayesian_fn', 'kurtosis': 'check_entry_kurtosis_fn',
    'chi_square': 'check_entry_chi_square_fn',
}
EXIT_ARG = {
    'stoch': 'check_exit_stoch_fn', 'parabolic': 'check_exit_parabolic_fn',
    'ma': 'check_exit_ma_fn', 'rf': 'check_exit_rf_fn',
    'logreg': 'check_exit_logreg_fn', 'macd_cross': 'check_exit_macd_cross_fn',
    'rsi_rev': 'check_exit_rsi_reversal_fn', 'bollinger': 'check_exit_bollinger_fn',
    'ema_cross': 'check_exit_ema_crossover_fn', 'rsi_div': 'check_exit_rsi_divergence_fn',
    'ichimoku': 'check_exit_ichimoku_fn', 'zscore': 'check_exit_zscore_fn',
    'autocorr': 'check_exit_autocorr_fn', 'hurst': 'check_exit_hurst_fn',
    'lrc': 'check_exit_lrc_fn', 'percentile': 'check_exit_percentile_fn',
    'runs': 'check_exit_runs_fn', 'coint': 'check_exit_coint_fn',
    'sharpe': 'check_exit_sharpe_fn', 'skewness': 'check_exit_skewness_fn',
    'bayesian': 'check_exit_bayesian_fn', 'kurtosis': 'check_exit_kurtosis_fn',
    'chi_square': 'check_exit_chi_square_fn',
}

N = 210  # >= 202: RSI-Rev требует прогрев EMA200


class FakePos:
    __slots__ = ('symbol', 'magic')

    def __init__(self, symbol, magic):
        self.symbol = symbol
        self.magic = magic


def fake_mt5(positions, ticks):
    return types.SimpleNamespace(
        positions_get=lambda *a, **k: list(positions),
        symbol_info_tick=lambda symbol: ticks.get(symbol),
        ACCOUNT_MARGIN_MODE_RETAIL_HEDGING='hedging',
    )


def make_df():
    idx = pd.date_range('2026-09-01', periods=N, freq='h')
    base = 1.1000
    return pd.DataFrame({
        'time': idx,
        'open': base + np.arange(N) * 0.0001,
        'high': base + np.arange(N) * 0.0001 + 0.0002,
        'low': base + np.arange(N) * 0.0001 - 0.0002,
        'close': base + np.arange(N) * 0.0001,
        'volume': np.full(N, 100.0),
    })


def make_info():
    return types.SimpleNamespace(digits=5, point=0.0001)


def make_symbol_data(missing=()):
    sd = {}
    for sym in SYMBOLS:
        if sym in missing:
            sd[sym] = {'df_h1': None, 'info': None}
        else:
            sd[sym] = {'df_h1': make_df(), 'info': make_info(), 'current_hour': None}
    return sd


def build_ticks(sc):
    ticks = {}
    for sym in SYMBOLS:
        if sym in sc.get('ticks_none', []):
            ticks[sym] = None
        else:
            base = 157.0 if sym == 'USDJPYrfd' else 0.8 if sym == 'USDCHFrfd' else 1.1
            ticks[sym] = types.SimpleNamespace(bid=base, ask=base + (0.01 if sym == 'USDJPYrfd' else 0.0001))
    return ticks


def make_calc(sig_col, extra=()):
    vals = np.arange(N) * 0.001 + 0.5

    def calc_stub(df, s, *a, **k):
        out = df.copy()
        if sig_col == 'trend_up':
            out['trend_up'] = vals
            out['trend_down'] = 1.0 - vals
        else:
            out[sig_col] = vals
        for c in extra:
            out[c] = vals
        return out

    return calc_stub


def make_entry(direction):
    def entry_fn(*a, **k):
        return direction

    return entry_fn


def make_exit(result):
    def exit_fn(*a, **k):
        return result

    return exit_fn


def mk(symbol, stype, param_key, magic, extra=None, position=None):
    s = {'symbol': symbol, 'type': stype, 'param_key': param_key, 'magic': magic,
         'sl_points': 300, 'tp_points': 1200, 'lot': 0.01}
    if extra:
        s.update(extra)
    if position is not None:
        s['position'] = {'direction': position, 'entry_price': 1.0,
                         'entry_time': NOW, 'ticket': 50_000 + magic, 'lot': 0.01}
    return s


def skey(s):
    return f"{s['symbol']}_{s['type']}_{s['param_key']}"


class LogWriter:
    def __init__(self, log):
        self._log = log

    def write(self, s):
        if s:
            for line in s.rstrip('\n').split('\n'):
                if line:
                    self._log.append('P|' + line)
        return len(s)

    def flush(self):
        pass


def run_scenario(impl, sc, log):
    strategies = {skey(s): s for s in deepcopy(sc['strategies'])}
    sd = make_symbol_data(missing=sc.get('missing_info', ()))
    positions = [FakePos(*p) for p in sc.get('positions', [])]
    ticks = build_ticks(sc)
    se._MISSING_INFO_WARNED = set()

    counter = {'n': 0}

    def send_fn(symbol, direction, lot, sl, tp, magic, comment, symbol_data, risk_params=None):
        counter['n'] += 1
        ticket = 10_000 + counter['n']
        log.append(f"SEND {symbol} {direction} lot={lot} sl={sl:.6f} tp={tp:.6f} "
                   f"magic={magic} comment={comment!r}")
        return ticket

    def close_fn(symbol, ticket, direction, magic, symbol_data):
        log.append(f"CLOSE_ORDER {symbol} t={ticket} dir={direction} magic={magic}")
        return 1.23456

    def record_close(key, s, now, exit_price, reason, symbol_data, record_trade_fn,
                     journal_df=None, JOURNAL_FILE=None):
        log.append(f"RECORD_CLOSE {key} price={exit_price:.6f} reason={reason}")

    def handle_gone(key, s, now, symbol_data, get_price_fn, record_close_fn, record_trade_fn):
        return key in sc.get('gone_keys', set())

    kw = dict(
        now=NOW,
        active_strategies=strategies,
        symbol_data=sd,
        send_order_fn=send_fn,
        close_order_fn=close_fn,
        get_deal_exit_price_fn=lambda *a, **k: 1.11111,
        _record_close_fn=record_close,
        record_trade_fn=lambda *a, **k: None,
        journal_df=None,
        JOURNAL_FILE=None,
        risk_cfg=RiskParams(
            max_total_positions=sc.get('max_total_positions', 999999),
            max_per_symbol=sc.get('max_per_symbol', 999999),
        ),
    )

    entry_dirs = dict(sc.get('entry_dirs', {}))
    exit_flags = dict(sc.get('exit_flags', {}))
    for t in TYPES:
        calc_none = sc.get('calc_none', {}).get(t, False)
        kw[CALC_ARG[t]] = None if calc_none else make_calc(sig_col_for(t), extra_cols(t))
        kw[ENTRY_ARG[t]] = make_entry(entry_dirs.get(t, 'long'))
        kw[EXIT_ARG[t]] = make_exit(exit_flags.get(t, True))

    old_mt5 = se.mt5
    se.mt5 = fake_mt5(positions, ticks)
    try:
        with redirect_stdout(LogWriter(log)):
            impl(**kw)
    finally:
        se.mt5 = old_mt5


def sig_col_for(t):
    return {
        'stoch': 'k', 'parabolic': 'sar', 'ma': 'ma', 'rf': 'rf_signal',
        'logreg': 'lr_signal', 'macd_cross': 'signal', 'rsi_rev': 'signal',
        'bollinger': 'signal', 'ema_cross': 'signal', 'rsi_div': 'signal',
        'ichimoku': 'signal', 'zscore': 'zscore', 'autocorr': 'acf',
        'hurst': 'trend_up', 'lrc': 'lr_signal', 'percentile': 'percentile',
        'runs': 'z_stat', 'coint': 'spread_z', 'sharpe': 'sharpe',
        'skewness': 'skewness', 'bayesian': 'trend_up', 'kurtosis': 'trend_up',
        'chi_square': 'trend_up',
    }[t]


def extra_cols(t):
    if t in ('hurst', 'bayesian', 'kurtosis', 'chi_square'):
        return ()
    if t == 'rsi_rev':
        return ('rsi', 'trend')
    return ()


# ───────────── СЦЕНАРИИ ─────────────
def scenario_entry_all():
    sc = {'name': 'ENTRY_ALL_TYPES', 'strategies': [], 'entry_dirs': {}}
    for i, t in enumerate(TYPES):
        sym = SYMBOLS[i % len(SYMBOLS)]
        extra = {'parabolic_max': 0.20 + (i % 3) * 0.1} if t == 'parabolic' else None
        sc['strategies'].append(mk(sym, t, f'P{i}', 800_000 + i, extra=extra))
        sc['entry_dirs'][t] = 'short' if i % 2 else 'long'
    return sc


def scenario_exit_all():
    sc = {'name': 'EXIT_ALL_TYPES', 'strategies': [], 'exit_flags': {}}
    for i, t in enumerate(TYPES):
        sym = SYMBOLS[i % len(SYMBOLS)]
        sc['strategies'].append(mk(sym, t, f'P{i}', 810_000 + i, position='long'))
    for i, t in enumerate(TYPES):
        sc['exit_flags'][t] = (i % 3 != 0)
    sc['gone_keys'] = {f"{SYMBOLS[0]}_{TYPES[0]}_P0"}
    return sc


def scenario_parabolic_max():
    return {
        'name': 'PARABOLIC_MAX_DISTINCT',
        'strategies': [
            mk('USDCADrfd', 'parabolic', 'S0.04', 800_100, extra={'parabolic_max': 0.2}),
            mk('USDCADrfd', 'parabolic', 'S0.04', 800_101, extra={'parabolic_max': 0.3}),
        ],
        'positions': [('USDCADrfd', 800_100)],
    }


def scenario_limits():
    return {
        'name': 'LIMIT_PER_SYMBOL',
        'strategies': [mk('EURUSDrfd', 'rf', 'K_x', 800_200)],
        'positions': [('EURUSDrfd', 999_999)],
        'max_per_symbol': 1,
    }


def scenario_tick_none():
    return {
        'name': 'TICK_NONE',
        'strategies': [
            mk('EURUSDrfd', 'stoch', 'K7', 800_300),
            mk('GBPUSDrfd', 'ma', 'M135', 800_301),
        ],
        'ticks_none': ['EURUSDrfd'],
    }


def scenario_missing_info():
    return {
        'name': 'MISSING_DF_INFO',
        'strategies': [mk('EURUSDrfd', 'stoch', 'K7', 800_400)],
        'missing_info': ['EURUSDrfd'],
    }


def scenario_unknown():
    return {'name': 'UNKNOWN_TYPE', 'strategies': [mk('EURUSDrfd', 'foobar', 'X', 800_500)]}


def scenario_missing_modules():
    return {
        'name': 'RF_LOGREG_MISSING_MODULE',
        'strategies': [
            mk('EURUSDrfd', 'rf', 'Kc', 800_600),
            mk('GBPUSDrfd', 'logreg', 'Kc', 800_601),
            mk('USDJPYrfd', 'ma', 'M100', 800_602),
        ],
        'calc_none': {'rf': True, 'logreg': True},
    }


def build_scenarios():
    return [
        scenario_entry_all(),
        scenario_exit_all(),
        scenario_parabolic_max(),
        scenario_limits(),
        scenario_tick_none(),
        scenario_missing_info(),
        scenario_unknown(),
        scenario_missing_modules(),
    ]


def run_scenarios(impl, scenarios):
    se._MISSING_INFO_WARNED = set()
    log = []
    for sc in scenarios:
        log.append(f"### {sc['name']}")
        run_scenario(impl, sc, log)
    return log


def diff_stdout(a, b):
    for line in difflib.unified_diff(a, b, fromfile='NEW/ТЕКУЩИЙ', tofile='ЭТАЛОН', lineterm=''):
        print(line)


def main():
    ap = argparse.ArgumentParser(description='Parity-тест check_active_signals')
    ap.add_argument('mode', choices=['golden', 'check'])
    args = ap.parse_args()

    scenarios = build_scenarios()
    golden_path = 'journals/parity_golden.txt'

    if args.mode == 'golden':
        log = run_scenarios(se.check_active_signals, scenarios)
        with open(golden_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(log) + '\n')
        print(f"GOLDEN сохранён: {len(log)} строк -> {golden_path}")
        return

    # --check
    ok = True
    current_log = run_scenarios(se.check_active_signals, scenarios)

    ref = getattr(se, '_obsolete_check_active_signals', None)
    if ref is not None:
        ref_log = run_scenarios(ref, scenarios)
        if ref_log == current_log:
            print(f"A/B: ОК — новая реализация и архив дают одинаковый лог ({len(current_log)} строк)")
        else:
            ok = False
            print("A/B: РАСХОЖДЕНИЕ (текущий vs архив):")
            diff_stdout(current_log, ref_log)

    try:
        with open(golden_path, 'r', encoding='utf-8') as f:
            golden = f.read().splitlines()
        if golden == current_log:
            print(f"golden: ОК — совпадает с {golden_path} ({len(current_log)} строк)")
        else:
            ok = False
            print(f"golden: РАСХОЖДЕНИЕ c {golden_path}:")
            diff_stdout(current_log, golden)
    except FileNotFoundError:
        print(f"golden: файл {golden_path} не найден — пропущено (нужен `--golden`)")

    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()