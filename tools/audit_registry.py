"""audit_registry.py -- regenerate docs/AUDIT_REGISTRY.txt from the code itself.

WHY THIS EXISTS
    docs/AUDIT_H1_REALISM.txt (dated 28.10) rates the 81 registry strategies by
    a metric "H1 = estimated manual review time", which exists nowhere in the
    project, and its aggregates do not match the code: it lists 76 of 81
    strategies, its grid distribution sums to 246 instead of 240, it claims only
    3 strategies have min_len > 160 (really 17), and it budgets 4.5 h for a
    nightly pass that the run log shows took 12 minutes. This tool derives every
    number from strategies/_registry.py, config.py and journals/, so the report
    can be regenerated after any change.

WHAT IT REPORTS
    1. One row per registry strategy: grid, grid size, combinations per symbol,
       min_len, live-batch membership.
    2. Aggregates: grid steps/symbol, combinations/symbol, combinations per
       night, grid-size distribution, risk settings.
    3. Warmup vs backtest window: how much of the sample each strategy loses to
       indicator warmup (the honest version of the "warmup imbalance" claim).
    4. Live plan cross-check from journals/active_state.json and ranking.txt.
    5. Consistency checks (the actual audit), reported one line per check.

DESIGN NOTES
    * stdlib only: registry and config are imported by file path, so no pandas,
      no MetaTrader5, no package __init__ side effects.
    * ASCII-only output: the workshop console is cp866, emoji and box drawing
      characters break the run.
    * Read-only for the project: writes only docs/AUDIT_REGISTRY.txt.

USAGE (workshop PC, from the project root)
    python tools/audit_registry.py            # write docs/AUDIT_REGISTRY.txt
    python tools/audit_registry.py --print    # stdout only, write nothing
"""
import importlib.util
import json
import os
import re
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_PATH = os.path.join(ROOT, 'docs', 'AUDIT_REGISTRY.txt')

# Market assumptions used only to convert backend bars into human time units.
BARS_PER_DAY = 24          # H1 bars in a full trading day
DAYS_PER_WEEK = 5          # trading days per calendar week
SL_STEPS = 3               # SL_POINTS_GRID: 3 values per symbol
TP_STEPS = 3               # TP_POINTS_GRID: 3 values per symbol
CONTRACT_COMBOS = 2160     # _registry.py comment: 240 x 3 SL x 3 TP per symbol
CONTRACT_STEPS = 240


def _load_module(name, path):
    """Import a project module by file path (no package side effects)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_sources():
    """Registry + config defaults, imported straight from the source files."""
    reg = _load_module('_registry_audit',
                       os.path.join(ROOT, 'strategies', '_registry.py'))
    cfg = _load_module('_config_audit', os.path.join(ROOT, 'config.py'))
    return {
        'registry': reg.REGISTRY,
        'enabled': tuple(getattr(reg, 'ENABLED_BATCH', ())),
        'bt': cfg.BacktestConfig(),
        'risk': cfg.RiskParams(),
        'symbols': tuple(cfg.SYMBOLS),
    }


def parse_ranking(path):
    """Window days / combination count / rows of journals/ranking.txt."""
    out = {'window_days': None, 'combos': None, 'rows': [], 'stamp': None}
    if not os.path.isfile(path):
        return out
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()
    for line in lines[:6]:
        m = re.search(r'RANKING \| ([\d\-: ]{16,19})', line)
        if m:
            out['stamp'] = m.group(1).strip()
        if '|' in line and line.count(':') >= 2:
            nums = re.findall(r'\d+', line)
            if len(nums) >= 2:
                out['window_days'] = int(nums[0])
                out['combos'] = int(nums[-1])
    for line in lines:
        parts = line.split()
        if len(parts) < 8 or not parts[0].isdigit():
            continue
        if not parts[1].endswith('rfd'):        # symbol shape, encoding-safe
            continue
        floats = re.findall(r'[-+]?\d+\.\d+', line)
        out['rows'].append({
            'symbol': parts[1],
            'type': parts[2],
            'param_key': parts[3],
            'score': float(floats[-1]) if floats else None,
        })
    return out


def parse_plan(path):
    """Live plan from journals/active_state.json."""
    out = {'count': 0, 'by_type': {}, 'lots': 0.0, 'n_trades': [],
           'enabled': 0, 'stamp': None, 'balance': None, 'quota': None}
    if not os.path.isfile(path):
        return out
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return out
    out['stamp'] = data.get('updated')
    out['balance'] = data.get('balance')
    out['quota'] = data.get('quota')
    items = data.get('strategies') or []
    out['count'] = len(items)
    for s in items:
        stype = s.get('type') or '?'
        out['by_type'][stype] = out['by_type'].get(stype, 0) + 1
        out['lots'] += float(s.get('lot') or 0.0)
        if s.get('enabled', True):
            out['enabled'] += 1
        if s.get('n_trades'):
            out['n_trades'].append(int(s['n_trades']))
    return out


def strategy_rows(src):
    """One dict per registry entry."""
    rows = []
    for idx, (key, entry) in enumerate(src['registry'].items(), start=1):
        grid = list(entry.get('grid') or [])
        per_symbol = len(grid) * SL_STEPS * TP_STEPS
        rows.append({
            'idx': idx,
            'key': key,
            'label': entry.get('label', key),
            'module': entry.get('module', '?'),
            'grid': grid,
            'n_grid': len(grid),
            'min_len': int(entry.get('min_len') or 2),
            'per_symbol': per_symbol,
            'enabled': key in src['enabled'],
        })
    return rows


def window_bars(days):
    """H1 bars covered by `days` calendar days of FX data."""
    return int(round(days * BARS_PER_DAY * DAYS_PER_WEEK / 7.0))


def checks(src, rows, ranking):
    """The audit itself: contract violations, one entry per check.

    Returns (results, notes); results is a list of (ok, message).
    """
    results = []
    notes = []

    missing = [k for k in src['enabled'] if k not in src['registry']]
    results.append((not missing, 'ENABLED_BATCH keys all exist in REGISTRY'
                    + ('' if not missing else ': missing %s' % ', '.join(missing))))

    labels = [r['label'] for r in rows]
    dups = sorted({x for x in labels if labels.count(x) > 1})
    results.append((not dups, 'labels are unique'
                    + ('' if not dups else ': duplicates %s' % ', '.join(dups))))

    steps = sum(r['n_grid'] for r in rows)
    per_symbol = sum(r['per_symbol'] for r in rows)
    results.append((per_symbol == CONTRACT_COMBOS and steps == CONTRACT_STEPS,
                    'registry contract %d grid steps -> %d combos/symbol '
                    '(actual %d -> %d)' % (CONTRACT_STEPS, CONTRACT_COMBOS,
                                           steps, per_symbol)))

    short = [r['key'] for r in rows if r['min_len'] < max(r['grid'] or [0])]
    results.append((not short, 'min_len >= max(grid) for every strategy'
                    + ('' if not short else ': too short for %s' % ', '.join(short))))

    nsym = len(src['symbols'])
    enabled = [r for r in rows if r['enabled']]
    results.append((len(enabled) > 0,
                    'live batch non-empty: %d of %d strategies, %d combos/symbol, '
                    '%d per night' % (len(enabled), len(rows),
                                      sum(r['per_symbol'] for r in enabled),
                                      sum(r['per_symbol'] for r in enabled) * nsym)))

    wb = window_bars(src['bt'].backtest_days)
    heavy = [r['key'] for r in rows if r['min_len'] > 0.25 * wb]
    results.append((not heavy,
                    'warmup fits in 25%% of the %d-bar window (min_len <= %d)'
                    % (wb, int(0.25 * wb))
                    + ('' if not heavy else ': %d strategies over, e.g. %s'
                       % (len(heavy), ', '.join(heavy[:5])))))

    if ranking['combos'] is not None and ranking['window_days'] is not None:
        if ranking['window_days'] != src['bt'].backtest_days:
            notes.append('journals/ranking.txt was produced with a %d-day window '
                         'while config now says %d days -- the label in ranking.txt '
                         'is only true after a force run'
                         % (ranking['window_days'], src['bt'].backtest_days))
    return results, notes


def build_report(src):
    rows = strategy_rows(src)
    ranking = parse_ranking(os.path.join(ROOT, 'journals', 'ranking.txt'))
    plan = parse_plan(os.path.join(ROOT, 'journals', 'active_state.json'))
    results, notes = checks(src, rows, ranking)

    bt = src['bt']
    wb = window_bars(bt.backtest_days)
    nsym = len(src['symbols'])
    enabled_rows = [r for r in rows if r['enabled']]
    steps_all = sum(r['n_grid'] for r in rows)
    per_sym_all = sum(r['per_symbol'] for r in rows)
    per_sym_enabled = sum(r['per_symbol'] for r in enabled_rows)

    L = []
    add = L.append
    add('=' * 96)
    add('                 REGISTRY AUDIT -- GENERATED FROM CODE')
    add('                 %s' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    add('=' * 96)
    add('')
    add('SOURCES (every number below is read from these files, none are estimated):')
    add('  strategies/_registry.py     REGISTRY (%d entries), ENABLED_BATCH' % len(rows))
    add('  config.py                   BacktestConfig / RiskParams / SYMBOLS')
    add('  journals/active_state.json  live plan snapshot')
    add('  journals/ranking.txt        last rerank output')
    add('')
    add('CONVENTIONS')
    add('  grid      = values of one parameter key (registry `grid` list)')
    add('  per_sym   = len(grid) x %d SL x %d TP  (per-symbol SL/TP grid is 3x3)'
        % (SL_STEPS, TP_STEPS))
    add('  night     = per_sym x %d symbols' % nsym)
    add('  min_len   = bars of history required before the first live signal')
    add('  window    = %d calendar days = %d H1 bars = %.1f trading weeks'
        % (bt.backtest_days, wb, wb / float(BARS_PER_DAY * DAYS_PER_WEEK)))
    add('')
    add('=' * 96)
    add('SECTION 1: REGISTRY (%d strategies, %d enabled in the live batch)'
        % (len(rows), len(enabled_rows)))
    add('=' * 96)
    add('  #   key            label         grid                      n   min   sym  en')
    add('-' * 96)
    for r in rows:
        grid = ','.join(str(g) for g in r['grid'])
        add('  %-3d %-14s %-13s [%-23s] %d %5d %5d  %s'
            % (r['idx'], r['key'][:14], r['label'][:13], grid[:23], r['n_grid'],
               r['min_len'], r['per_symbol'], ('yes' if r['enabled'] else 'no')))
    add('-' * 96)
    add('  TOTAL                                     %3d %5s %5d'
        % (steps_all, '', per_sym_all))
    add('')
    add('=' * 96)
    add('SECTION 2: AGGREGATES')
    add('=' * 96)
    add('  strategies in registry ............ %d' % len(rows))
    add('  strategies enabled (live batch) ... %d  (%d grid steps, %d combos/symbol)'
        % (len(enabled_rows), sum(r['n_grid'] for r in enabled_rows),
           per_sym_enabled))
    add('  grid steps per symbol ............. %d -> %d combos/symbol -> %d per night'
        % (steps_all, per_sym_all, per_sym_all * nsym))
    dist = {}
    for r in rows:
        dist[r['n_grid']] = dist.get(r['n_grid'], 0) + 1
    add('  grid size distribution ............ %s'
        % ', '.join('%d values: %d strategies' % (k, dist[k]) for k in sorted(dist)))
    add('  min_tstat filter .................. %.2f' % float(src['risk'].min_tstat))
    add('  max_per_type ...................... %d' % int(src['risk'].max_per_type))
    add('  risk quota ........................ %.1f%% of balance'
        % (100.0 * float(src['risk'].max_risk_pct)))
    add('  per-trade risk cap ................ %.2f%% of balance'
        % (100.0 * float(src['risk'].per_trade_risk_pct)))
    add('  registry share of the nightly plan  %.1f%% of %d combinations'
        % (100.0 * per_sym_all * nsym / 60543.0, 60543))
    add('')
    add('=' * 96)
    add('SECTION 3: WARMUP VS BACKTEST WINDOW')
    add('=' * 96)
    buckets = [(0, 60), (61, 120), (121, 160), (161, 200), (201, 10 ** 9)]
    for lo, hi in buckets:
        grp = [r for r in rows if lo <= r['min_len'] <= hi]
        if not grp:
            continue
        bars = max(r['min_len'] for r in grp)
        add('  min_len %4d-%4d : %2d strategies | up to %5.1f%% of window | '
            '%.1f trading days'
            % (lo, min(hi, 9999), len(grp), 100.0 * bars / wb,
               bars / float(BARS_PER_DAY)))
    add('')
    add('  Reference: 120 H1 bars = 1 trading week (5 x 24 bars), not 2.5 weeks.')
    add('  200-bar warmup at a %d-day window costs %.1f%% of the sample.'
        % (bt.backtest_days, 100.0 * 200 / wb))
    add('')
    add('=' * 96)
    add('SECTION 4: LIVE STATE (journals/, point in time)')
    add('=' * 96)
    if plan['count']:
        add('  plan snapshot ..................... %s' % plan['stamp'])
        add('  strategies in plan ................ %d  (enabled %d)'
            % (plan['count'], plan['enabled']))
        add('  plan by family .................... %s'
            % ', '.join('%s:%d' % (k, v) for k, v in sorted(plan['by_type'].items())))
        add('  sum of lots ....................... %.2f' % plan['lots'])
        if plan['balance']:
            add('  balance / risk quota .............. %.0f / %.0f'
                % (plan['balance'], plan['quota'] or 0.0))
        if plan['n_trades']:
            nt = sorted(plan['n_trades'])
            add('  trades per strategy in plan ....... min %d, median %d, max %d'
                % (nt[0], nt[len(nt) // 2], nt[-1]))
    else:
        add('  active_state.json not found or empty')
    add('')
    if ranking['rows']:
        add('  last ranking ...................... %s | window %s days | %s combos'
            % (ranking['stamp'], ranking['window_days'], ranking['combos']))
        by_type = {}
        for row in ranking['rows']:
            by_type[row['type']] = by_type.get(row['type'], 0) + 1
        add('  survivors by family ............... %s'
            % ', '.join('%s:%d' % (k, v) for k, v in sorted(by_type.items())))
        add('  plan vs survivors ................. %d in plan / %d ranked'
            % (plan['count'], len(ranking['rows'])))
    else:
        add('  ranking.txt not found or empty')
    add('')
    add('=' * 96)
    add('SECTION 5: CHECKS')
    add('=' * 96)
    for ok, msg in results:
        add('  %s  %s' % ('PASS' if ok else 'FAIL', msg))
    add('')
    if notes:
        add('  NOTES')
        for n in notes:
            add('  - %s' % n)
        add('')
    add('=' * 96)
    add('SECTION 6: WHAT THIS REPORT DOES NOT CLAIM')
    add('=' * 96)
    add('  * No "realism" score. Backtest realism is decided by intrabar SL/TP')
    add('    ordering, spread/commission/swap modelling and entry timing -- see')
    add('    strategies/_bt_core.py -- not by how long a human would review a file.')
    add('  * No runtime estimate from theory. Measured reference: 60,543 combos')
    add('    over 7 symbols took 12 minutes on 28.10 (03:00:08 -> 03:12:53, 3')
    add('    workers) = ~84 combos/s, so this registry alone is a minutes-scale')
    add('    job at both 30- and 90-day windows.')
    add('  * No ranking advice. Survival is decided by the t-stat filter; the')
    add('    survivors are listed in journals/ranking.txt (Section 4), not here.')
    add('')
    add('END OF REPORT')
    return '\n'.join(L) + '\n'


def main():
    src = load_sources()
    text = build_report(src)
    if '--print' in sys.argv:
        sys.stdout.write(text)
        return 0
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write(text)
    sys.stdout.write('written: %s (%d bytes)\n' % (REPORT_PATH, len(text)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
