"""Базовый класс для всех стратегий."""
import numpy as np
import pandas as pd


class BaseStrategy:
    """
    Базовый класс-шаблон для всех стратегий.
    Каждая новая стратегия наследуется и переопределяет:
      - calc_indicator(df, **params) -> df с колонками сигнала
      - check_entry(prev_signal, curr_signal) -> 'long' | 'short' | None
      - check_exit(prev_signal, curr_signal, direction) -> bool
      - NAME -> строковое имя для логов

    Общие методы (backtest, profit_rub) не переопределяются.
    """

    NAME = 'base'

    def __init__(self):
        pass

    # ── Переопределяется в подклассе ──
    def calc_indicator(self, df, **params):
        """Рассчитать индикатор/сигналы. Возвращает DataFrame с колонкой 'signal'."""
        return df

    def check_entry(self, prev_signal, curr_signal):
        """Вход: 'long', 'short' или None."""
        return None

    def check_exit(self, prev_signal, curr_signal, direction):
        """Выход: True если нужно закрыть позицию."""
        return False

    # ── Общие методы (не переопределяются) ──
    @staticmethod
    def profit_rub(entry, exit_price, tick_value, tick_size, lot, direction):
        """Рассчитать прибыль в рублях."""
        diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
        return (diff / tick_size) * tick_value * lot

    @staticmethod
    def backtest(df, sl_points, tp_points, point, tick_value, tick_size,
                 sim_lot=0.01, spread_points=0, **indicator_params):
        """
        Общий бэктест для всех стратегий.
        Подкласс должен реализовать calc_indicator, check_entry, check_exit.

        Возвращает (profit, n_trades, trade_profits).
        """
        df = self.calc_indicator(df.copy(), **indicator_params)
        sl_dist = sl_points * point
        tp_dist = tp_points * point
        spread = spread_points * point

        if 'signal' not in df.columns:
            return 0.0, 0, []

        profit = 0.0
        n_trades = 0
        position = None
        trade_profits = []

        for i in range(1, len(df)):
            prev_signal = df['signal'].iloc[i - 1]
            curr_signal = df['signal'].iloc[i]
            curr_close = df['close'].iloc[i]
            current_high = df['high'].iloc[i]
            current_low = df['low'].iloc[i]

            # ── Проверка выхода ──
            if position:
                exited = False
                p = 0.0
                d = position['direction']

                if d == 'long':
                    if current_low <= position['sl']:
                        p = BaseStrategy.profit_rub(position['entry'], position['sl'],
                                                    tick_value, tick_size, sim_lot, 'long')
                        exited = True
                    elif current_high >= position['tp']:
                        p = BaseStrategy.profit_rub(position['entry'], position['tp'],
                                                    tick_value, tick_size, sim_lot, 'long')
                        exited = True
                    elif BaseStrategy().check_exit(prev_signal, curr_signal, 'long'):
                        p = BaseStrategy.profit_rub(position['entry'], curr_close,
                                                    tick_value, tick_size, sim_lot, 'long')
                        exited = True
                else:
                    if current_high >= position['sl']:
                        p = BaseStrategy.profit_rub(position['entry'], position['sl'],
                                                    tick_value, tick_size, sim_lot, 'short')
                        exited = True
                    elif current_low <= position['tp']:
                        p = BaseStrategy.profit_rub(position['entry'], position['tp'],
                                                    tick_value, tick_size, sim_lot, 'short')
                        exited = True
                    elif BaseStrategy().check_exit(prev_signal, curr_signal, 'short'):
                        p = BaseStrategy.profit_rub(position['entry'], curr_close,
                                                    tick_value, tick_size, sim_lot, 'short')
                        exited = True

                if exited:
                    p -= (spread / tick_size) * tick_value * sim_lot
                    profit += p
                    n_trades += 1
                    trade_profits.append(p)
                    position = None

            # ── Проверка входа ──
            if position is None:
                entry_dir = BaseStrategy().check_entry(prev_signal, curr_signal)
                if entry_dir == 'long':
                    entry = curr_close + spread
                    position = {'direction': 'long', 'entry': entry,
                                'sl': entry - sl_dist, 'tp': entry + tp_dist}
                elif entry_dir == 'short':
                    entry = curr_close - spread
                    position = {'direction': 'short', 'entry': entry,
                                'sl': entry + sl_dist, 'tp': entry - tp_dist}

        return profit, n_trades, trade_profits
