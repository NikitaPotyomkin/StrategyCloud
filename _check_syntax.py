# -*- coding: utf-8 -*-
"""Quick syntax check for 11 fixed strategies."""
import sys
sys.path.insert(0, r'C:\Users\UseR\AppData\Roaming\MetaQuotes\Terminal\FA97EA291D4188820508F9D2B5AAD50F\MQL5\Files\PythonProjects\StrategyCloud')

files = [
    'strategies/mr_rsi_sma.py',
    'strategies/bc_volume_confirm.py',
    'strategies/bc_adaptive_donchian.py',
    'strategies/mi_rsi_bb_vol.py',
    'strategies/mi_adx_rsi_ma.py',
    'strategies/mi_stoch_atr_vol.py',
    'strategies/advstat_hurst.py',
    'strategies/volprof_effort_result.py',
    'strategies/osc_aroon.py',
    'strategies/osc_ehlers_stoch.py',
    'strategies/stat_adf_regime.py',
]

ok = True
for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as fh:
            compile(fh.read(), f, 'exec')
        print(f'✓ {f}')
    except SyntaxError as e:
        print(f'✗ {f}: {e}')
        ok = False

if ok:
    print('\n=== ВСЕ ФАЙЛЫ КОМПИЛИРУЮТСЯ ===')
else:
    print('\n=== ЕСТЬ ОШИБКИ ===')
    sys.exit(1)
