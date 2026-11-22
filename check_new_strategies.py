#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Проверка 35 новых standalone стратегий."""
import py_compile
import sys
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'

files = [
    'strategies/regime_cusum_ret.py',
    'strategies/regime_bocpd_proxy.py',
    'strategies/regime_markov_quantile.py',
    'strategies/regime_duration.py',
    'strategies/regime_stress_index.py',
    'strategies/cyc_fft_dominant.py',
    'strategies/cyc_wavelet_energy.py',
    'strategies/cyc_hilbert_phase.py',
    'strategies/cyc_bandpass.py',
    'strategies/cyc_spectral_entropy.py',
    'strategies/anom_liquidity_hole.py',
    'strategies/anom_stop_run.py',
    'strategies/anom_spread_blowout.py',
    'strategies/anom_long_wick.py',
    'strategies/anom_huge_volume.py',
    'strategies/struct_liquidity_sweep.py',
    'strategies/struct_swing_bos.py',
    'strategies/struct_fvg_imbalance.py',
    'strategies/struct_equal_highs.py',
    'strategies/struct_range_expansion.py',
    'strategies/stat_adf_regime.py',
    'strategies/stat_vr_ratio.py',
    'strategies/stat_ljung_box.py',
    'strategies/stat_ks_change.py',
    'strategies/stat_autocorr_abs.py',
    'strategies/port_live_vs_bt_gate.py',
    'strategies/port_live_sharpe_rank.py',
    'strategies/port_min_live_trades.py',
    'strategies/port_alpha_decay.py',
    'strategies/port_kill_rule_live.py',
    'strategies/sess_transition_ldn.py',
    'strategies/sess_asian_compress.py',
    'strategies/sess_hour_of_day.py',
    'strategies/volprof_poc_break.py',
    'strategies/volprof_cvd_div.py',
]

errors = []
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f'OK: {f}')
    except Exception as e:
        errors.append((f, str(e)))
        print(f'ERROR: {f}: {e}')

print(f'\n{"="*60}')
print(f'SYNTAX CHECK: {len(files) - len(errors)}/{len(files)} files OK')
if errors:
    print(f'\n{len(errors)} FILES WITH ERRORS:')
    for f, err in errors:
        print(f'  - {f}: {err}')
    sys.exit(1)
else:
    print('All 35 files pass syntax check!')
