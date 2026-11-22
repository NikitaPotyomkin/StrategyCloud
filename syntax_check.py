import py_compile
import os
import glob

base_dir = 'strategies'
errors = []
checked = []

all_py = glob.glob(os.path.join(base_dir, '*.py'))

files_to_check = []
for f in all_py:
    fname = os.path.basename(f)
    if not fname.startswith('_'):
        files_to_check.append(f)
    elif fname == '_registry.py':
        files_to_check.append(f)

for fpath in sorted(files_to_check):
    fname = os.path.basename(fpath)
    try:
        py_compile.compile(fpath, doraise=True)
        checked.append(fname)
    except py_compile.PyCompileError as e:
        checked.append(fname)
        errors.append((fname, str(e)))

result = []
result.append('=== SYNTAX CHECK RESULTS ===')
result.append('Total files checked: ' + str(len(checked)))
result.append('')
if errors:
    result.append('SYNTAX ERRORS FOUND: ' + str(len(errors)))
    result.append('-' * 60)
    for fname, err in errors:
        result.append('  ' + fname)
        result.append('    ' + err)
        result.append('')
else:
    result.append('No syntax errors found.')
result.append('---')
result.append('All files passed syntax check.')

output = '\n'.join(result)
print(output)

with open('check_output.txt', 'w') as f:
    f.write(output)
