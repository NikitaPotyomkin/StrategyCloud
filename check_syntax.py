import py_compile
from pathlib import Path

strategies_dir = Path('strategies')
errors = []
success = 0

for f in sorted(strategies_dir.glob('*.py')):
    if f.name.startswith('_') and f.name != '__init__.py':
        continue
    try:
        py_compile.compile(str(f), doraise=True)
        success += 1
    except py_compile.PyCompileError as e:
        errors.append(f'{f.name}: {e}')

print(f'Syntax OK: {success} files')
if errors:
    print(f'Errors: {len(errors)}')
    for e in errors:
        print(f'  {e}')
else:
    print('No syntax errors')
