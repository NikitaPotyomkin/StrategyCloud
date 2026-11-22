import py_compile
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
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f'{f}: OK')
    except py_compile.PyCompileError as e:
        print(f'{f}: FAILED - {e}')
print('Done')
