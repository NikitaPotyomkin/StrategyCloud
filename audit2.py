# -*- coding: utf-8 -*-
import os, re, sys

strat_dir = 'strategies'
all_files = sorted([f[:-3] for f in os.listdir(strat_dir) 
                    if f.endswith('.py') 
                    and f not in ('__init__.py', '_registry.py', '_bt_core.py', 'base.py')])

with open(os.path.join(strat_dir, '_registry.py'), 'r', encoding='utf-8') as f:
    registry_content = f.read()

module_pattern = r"'module':\s*'([^']+)'"
registry_modules = re.findall(module_pattern, registry_content)
registry_set = set(registry_modules)

with open('main.py', 'r', encoding='utf-8') as f:
    main_content = f.read()

main_imports = sorted(list(set(re.findall(r'from strategies\.(\w+) import', main_content))))

missing_in_registry = [f for f in all_files if f not in registry_set]
in_main_not_registry = [m for m in main_imports if m not in registry_set]
in_registry_not_main = [m for m in registry_set if m not in main_imports]
in_registry_or_main = registry_set | set(main_imports)
not_integrated = [f for f in all_files if f not in in_registry_or_main]

out_lines = []
out_lines.append('TOTAL_FILES: %d' % len(all_files))
out_lines.append('IN_REGISTRY: %d' % len(registry_set))
out_lines.append('IN_MAIN: %d' % len(main_imports))
out_lines.append('MISSING_REGISTRY: %d' % len(missing_in_registry))
out_lines.append('MAIN_NOT_REGISTRY: %d' % len(in_main_not_registry))
out_lines.append('REGISTRY_NOT_MAIN: %d' % len(in_registry_not_main))
out_lines.append('NOT_INTEGRATED: %d' % len(not_integrated))
out_lines.append('---')
out_lines.append('MISSING_FROM_REGISTRY:')
for m in missing_in_registry:
    out_lines.append('  - %s' % m)
out_lines.append('---')
out_lines.append('IN_MAIN_NOT_REGISTRY:')
for m in in_main_not_registry:
    out_lines.append('  - %s' % m)
out_lines.append('---')
out_lines.append('NOT_INTEGRATED:')
for m in not_integrated:
    out_lines.append('  - %s' % m)

with open('audit_integration_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out_lines))

print('\n'.join(out_lines[:10]))
print('... (full result in audit_integration_result.txt)')
