"""Repair double-encoded Cyrillic in project .py files (UTF-8 bytes read as CP866).

Symptom in run.log / sources:  '╨Ш╤В╨╛╨│'  instead of  'Итог'.
Cause: UTF-8 bytes of Cyrillic were decoded as CP866 and saved back as UTF-8.
Fix:   line.encode('cp866').decode('utf-8')  -- exact inverse, per line.

Every Cyrillic mojibake line contains CP866 box-drawing chars (U+2500..U+257F),
because UTF-8 lead bytes D0/D1 map there. Correct Cyrillic never contains them,
so detection is safe and already-fixed lines are skipped (idempotent).

Usage:
    python tools/fix_mojibake.py --dry-run          # report only
    python tools/fix_mojibake.py                    # repair main.py in place
    python tools/fix_mojibake.py main.py wheel.py   # explicit files
    python tools/fix_mojibake.py --all              # every .py in the project

Exit code: 0 = nothing left to fix, 1 = unrepairable lines remain.
"""
import argparse
import io
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TARGETS = ('main.py',)
BACKUP_SUFFIX = '.mojibake.bak'
SKIP_DIRS = ('.git', '.venv', 'venv', '__pycache__', 'checkpoints', 'journals')


def has_mojibake(line):
    """True if the line contains CP866 box-drawing chars (mojibake marker)."""
    for ch in line:
        if '\u2500' <= ch <= '\u257f':
            return True
    return False


def repair_line(line):
    """Return the repaired line, or None when the CP866 round trip is not clean."""
    try:
        fixed = line.encode('cp866').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    if not fixed or has_mojibake(fixed):
        return None
    return fixed


def repair_file(path, dry_run):
    with io.open(path, 'r', encoding='utf-8', newline='') as f:
        lines = f.readlines()
    bad = [i for i, ln in enumerate(lines) if has_mojibake(ln)]
    fixed, skipped = 0, []
    for i in bad:
        new = repair_line(lines[i])
        if new is None:
            skipped.append(i + 1)
            continue
        lines[i] = new
        fixed += 1
    print('%-22s mojibake lines: %-4d fixed: %-4d skipped: %d'
          % (os.path.basename(path), len(bad), fixed, len(skipped)))
    if skipped:
        head = ', '.join(str(n) for n in skipped[:10])
        tail = ' ...' if len(skipped) > 10 else ''
        print('    unrepairable lines: %s%s' % (head, tail))
    if fixed and not dry_run:
        shutil.copy2(path, path + BACKUP_SUFFIX)
        with io.open(path, 'w', encoding='utf-8', newline='') as f:
            f.writelines(lines)
        print('    written, backup: %s%s' % (os.path.basename(path), BACKUP_SUFFIX))
    return fixed, len(skipped)


def iter_py_files():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith('.py'):
                yield os.path.join(base, name)


def main(argv):
    ap = argparse.ArgumentParser(description='Repair CP866 mojibake in .py files')
    ap.add_argument('files', nargs='*', help='files relative to the project root')
    ap.add_argument('--all', action='store_true', help='scan every .py in the project')
    ap.add_argument('--dry-run', action='store_true', help='report only, write nothing')
    args = ap.parse_args(argv)

    if args.all:
        targets = list(iter_py_files())
    else:
        names = args.files or DEFAULT_TARGETS
        targets = [n if os.path.isabs(n) else os.path.join(ROOT, n) for n in names]

    total_fixed, total_bad, total_skipped = 0, 0, 0
    for path in targets:
        if not os.path.isfile(path):
            print('%-22s MISSING' % os.path.basename(path))
            continue
        fixed, skipped = repair_file(path, args.dry_run)
        total_fixed += fixed
        total_skipped += skipped
        total_bad += fixed + skipped

    print('-' * 58)
    print('TOTAL mojibake lines: %d | fixed: %d | unrepairable: %d%s'
          % (total_bad, total_fixed, total_skipped,
             '  [dry run]' if args.dry_run else ''))
    return 0 if total_skipped == 0 else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
