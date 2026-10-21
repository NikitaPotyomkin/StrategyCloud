#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Аудит интеграции стратегий: файлы vs REGISTRY vs main.py"""
import os
import re

# 1. Все файлы стратегий
strat_dir = 'strategies'
all_files = sorted([f[:-3] for f in os.listdir(strat_dir) 
                    if f.endswith('.py') 
                    and f not in ('__init__.py', '_registry.py', '_bt_core.py', 'base.py')])
print(f'=== ВСЕГО ФАЙЛОВ СТРАТЕГИЙ: {len(all_files)} ===\n')

# 2. module names из REGISTRY (из файла _registry.py)
with open(os.path.join(strat_dir, '_registry.py'), 'r', encoding='utf-8') as f:
    registry_content = f.read()

# Извлекаем module='...' из каждого entry
module_pattern = r"'module':\s*'([^']+)'"
registry_modules = re.findall(module_pattern, registry_content)
registry_set = set(registry_modules)

print(f'=== В REGISTRY: {len(registry_set)} ===\n')

# Стратегии, которых НЕТ в REGISTRY
missing_in_registry = [f for f in all_files if f not in registry_set]
print(f'НЕТ в REGISTRY ({len(missing_in_registry)}):')
for m in missing_in_registry:
    print(f'  - {m}')

# 3. Импорты в main.py
with open('main.py', 'r', encoding='utf-8') as f:
    main_content = f.read()

main_imports = sorted(list(set(re.findall(r'from strategies\.(\w+) import', main_content))))
print(f'\n=== В main.py ИМПОРТОВ: {len(main_imports)} ===')

# Стратегии в main.py, которых нет в registry
in_main_not_registry = [m for m in main_imports if m not in registry_set]
print(f'\n=== В main.py НЕТ в REGISTRY ({len(in_main_not_registry)}): ===')
for m in in_main_not_registry:
    print(f'  - {m}')

# Стратегии в registry, которых нет в main.py
in_registry_not_main = [m for m in registry_set if m not in main_imports]
print(f'\n=== В REGISTRY НЕТ в main.py ({len(in_registry_not_main)}): ===')
for m in sorted(in_registry_not_main)[:30]:
    print(f'  - {m}')
if len(in_registry_not_main) > 30:
    print(f'  ... и ещё {len(in_registry_not_main) - 30}')

# ИТОГО: не интегрированы вообще (нет ни в registry, ни в main.py)
in_registry_or_main = registry_set | set(main_imports)
not_integrated = [f for f in all_files if f not in in_registry_or_main]
print(f'\n=== НЕ ИНТЕГРИРОВАНЫ НИЧЕГО ({len(not_integrated)}): ===')
for m in not_integrated:
    print(f'  - {m}')

# Сводка
print('\n' + '='*60)
print('СВОДКА:')
print(f'  Всего файлов стратегий:        {len(all_files)}')
print(f'  В REGISTRY:                    {len(registry_set)}')
print(f'  В main.py (импорты):           {len(main_imports)}')
print(f'  В REGISTRY и в main.py:        {len(registry_set & set(main_imports))}')
print(f'  Только в REGISTRY:             {len(in_registry_not_main)}')
print(f'  Только в main.py:              {len(in_main_not_registry)}')
print(f'  НЕ ИНТЕГРИРОВАНЫ:              {len(not_integrated)}')
print('='*60)
