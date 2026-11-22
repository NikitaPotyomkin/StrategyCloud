import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from strategies._registry import REGISTRY, ENABLED_BATCH, enabled_keys

print(f'REGISTRY entries: {len(REGISTRY)}')
print(f'ENABLED_BATCH entries: {len(ENABLED_BATCH)}')
print(f'Enabled (existing in REGISTRY): {len(enabled_keys())}')

# Check for _new suffix entries
new_entries = [k for k in ENABLED_BATCH if '_new' in k]
if new_entries:
    print(f'ERROR: {len(new_entries)} entries with _new suffix: {new_entries}')
else:
    print('OK: No _new suffix entries')

# Check all enabled modules exist
import importlib
missing = []
for key in enabled_keys():
    mod_name = REGISTRY[key]['module']
    try:
        importlib.import_module(f'strategies.{mod_name}')
    except ModuleNotFoundError:
        missing.append(f'{key} -> {mod_name}')

if missing:
    print(f'ERROR: {len(missing)} missing modules:')
    for m in missing:
        print(f'  {m}')
else:
    print('OK: All enabled modules importable')

# Check calc function names match actual files
mismatches = []
for key in enabled_keys():
    entry = REGISTRY[key]
    mod_name = entry['module']
    calc_name = entry['calc']
    
    try:
        mod = importlib.import_module(f'strategies.{mod_name}')
        if not hasattr(mod, calc_name):
            mismatches.append(f'{key}: module {mod_name} has no function {calc_name}')
    except:
        pass

if mismatches:
    print(f'ERROR: {len(mismatches)} calc name mismatches:')
    for m in mismatches:
        print(f'  {m}')
else:
    print('OK: All calc function names match')

print('\nDone.')
