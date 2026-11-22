"""Разовый расчёт family_score из чекпойнтов — без запуска торгового цикла.

Зачем: колонка score в Roadmap должна показывать оценку ЛЮБОГО семейства, даже
если оно целиком ниже порога рэнкинга. family_status.best_score для этого не
годится (он считается по уже отфильтрованным all_results), поэтому score берётся
из чекпойнтов символов — там лежат ВСЕ посчитанные комбинации.

Запуск (в папке StrategyCloud):
    python backfill_family_score.py
"""
from config import build_default_configs
import functions
import trades_db

app = build_default_configs()
rows = functions.family_score_rows(
    app.backtest_config.symbols, app.risk_params.min_score, 'backfill')
print(f'Строк (symbol, family): {len(rows)}')
written = trades_db.record_family_scores(rows)
print(f'Записано в family_score: {written}')
print('Топ-15 по best_score:')
for r in sorted(rows, key=lambda x: -x['best_score'])[:15]:
    print(f"  {r['symbol']:12s} {r['family']:16s} best={r['best_score']:8.2f} "
          f"комб={r['n_combos']:5d} >0: {r['n_positive']:5d} "
          f"средний={r['mean_score']:8.2f}")
