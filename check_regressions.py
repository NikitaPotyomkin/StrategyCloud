#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Проверка 8 новых standalone регрессий."""
import py_compile
import sys
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'

files = [
    'strategies/reg_theil_sen.py',
    'strategies/reg_ridge.py',
    'strategies/reg_lasso.py',
    'strategies/reg_polynomial.py',
    'strategies/reg_ransac.py',
    'strategies/reg_bayesian.py',
    'strategies/reg_elasticnet.py',
    'strategies/reg_quantile.py',
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
    print('All 8 regression files pass syntax check!')
