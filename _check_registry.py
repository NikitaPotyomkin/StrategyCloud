#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check REGISTRY vs ENABLED_BATCH and list differences."""
import sys
sys.path.insert(0, r'C:\Users\UseR\AppData\Roaming\MetaQuotes\Terminal\FA97EA291D4188820508F9D2B5AAD50F\MQL5\Files\PythonProjects\StrategyCloud')

from strategies._registry import REGISTRY, ENABLED_BATCH

print(f'REGISTRY keys: {len(REGISTRY)}')
print(f'ENABLED_BATCH: {len(ENABLED_BATCH)}')
print()

in_reg_not_enabled = sorted(k for k in REGISTRY.keys() if k not in ENABLED_BATCH)
in_enabled_not_reg = sorted(k for k in ENABLED_BATCH if k not in REGISTRY)

print('=== В REGISTRY, но НЕ в ENABLED_BATCH ===')
for k in in_reg_not_enabled:
    print(f'  - {k}')

print()
print('В ENABLED_BATCH, но НЕ в REGISTRY:')
for k in in_enabled_not_reg:
    print(f'  - {k}')

print()
print(f'Итого пропущено: {len(in_reg_not_enabled)} стратегий')
