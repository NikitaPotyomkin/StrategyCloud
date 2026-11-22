import py_compile
from pathlib import Path

files = [
    'strategies/stat_anderson_darling.py',
    'strategies/regime_duration.py',
    'strategies/regime_stress_index.py',
    'strategies/cyc_wavelet_energy.py',
    'strategies/cyc_hilbert_phase.py',
    'strategies/stat_adf_regime.py',
    'strategies/stat_autocorr_abs.py',
    'strategies/stat_permutation_entropy.py',
    'strategies/volprof_cvd_div.py',
    'strategies/port_alpha_decay.py',
]

ok = 0
err = 0
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f'OK: {f}')
        ok += 1
    except py_compile.PyCompileError as e:
        print(f'ERR: {f}: {e}')
        err += 1

print(f'\n{ok} OK, {err} ERR')
