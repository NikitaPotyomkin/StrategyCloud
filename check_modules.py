import sys
sys.path.insert(0, '.')

from strategies._registry import REGISTRY, ENABLED_BATCH

# Get all unique module names from REGISTRY
modules_needed = set(e['module'] for e in REGISTRY.values())
print(f'Modules in REGISTRY: {len(modules_needed)}')

# Check which exist
import os
missing = []
for mod in sorted(modules_needed):
    path = os.path.join('strategies', f'{mod}.py')
    if not os.path.exists(path):
        missing.append(mod)

if missing:
    print(f'Missing files: {len(missing)}')
    for m in missing:
        print(f'  {m}.py')
else:
    print('All modules exist on disk')

# Count by prefix
from collections import Counter
prefixes = Counter()
for mod in modules_needed:
    prefix = mod.split('_')[0]
    prefixes[prefix] += 1

print(f'\nBy prefix: {dict(prefixes.most_common(20))}')
