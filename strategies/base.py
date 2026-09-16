from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

class BaseStrategy:
    """Базовый класс. Конкретная стратегика переопределяет:
    - _calc_indicator(df) -> df с нужными колонками
    - check_entry_signal() -> 'long' | 'short' | None
    - check_exit_signal() -> bool
    """

    D_PERIOD = 3
    SLOWING = 3
    OVERSOLD = 20
    OVERBOUGHT = 80

    def __init__(self, symbol, sc_id, k_period, sl_points, tp_points, magic,
                 currency, sim_lot, min_real_lot, window_days,
                 point, tick_value, tick_size, digits):
        self.symbol = symbol
        self.sc_id = sc_id
        self.magic = magic
        self.sl_points = sl_points
        self.tp_points = tp_points
        self.currency = currency
        self.sim_lot = sim_lot
        self.min_real_lot = min_real_lot
        self.window_days = window_days
        self.point = point
        self.tick_value = tick_value
        self.tick_size = tick_size
        self.digits = digits
        self.sl_dist = sl_points * point
        self.tp_dist = tp_points * point

        # Имя стратегии задаёт подкласс
        if not hasattr(self, 'name'):
            self.name = f"{sc_id}_{currency}_H1"

        self.df_h1 = None
        self.current_hour = None
        self.forming_bar = None
        self.signal_checked = False
        self.position = None
        self.allocated_lot = 0.0
        self.mode = "paper"
        self.window_profit = 0.0
        self.accumulated_profit = 0.0

    # ── Переопределяется в подклассе ──
    def _calc_indicator(self, df):
        return df

    def check_entry_signal(self):
        return None

    def check_exit_signal(self):
        return False

    # ── Общие методы ──
    def init_history(self, h1_base):
        if h1_base is None or len(h1_base) < 25:
            return False
        self.df_h1 = self._calc_indicator(h1_base.copy())
        self.current_hour = (self.df_h1.index[-1] + timedelta(hours=1)).replace(
            minute=0, second=0, microsecond=0)
        self.forming_bar = None
        self.signal_checked = False
        return True

    def update_bar(self, bid, ask, now):
        bar_hour = now.replace(minute=0, second=0, microsecond=0)
        finalized = False
        if bar_hour != self.current_hour:
            if self.forming_bar is not None:
                new_row = pd.DataFrame(
                    {'open': self.forming_bar['open'], 'high': self.forming_bar['high'],
                     'low': self.forming_bar['low'], 'close': self.forming_bar['close']},
                    index=pd.DatetimeIndex([self.current_hour])
                )
                self.df_h1 = pd.concat([self.df_h1, new_row])
                self.df_h1 = self._calc_indicator(self.df_h1)
                self.signal_checked = False
                finalized = True
                print()
                print(f"[{self.name}] Бар {self.current_hour} закрыт")
            self.current_hour = bar_hour
            self.forming_bar = {'open': ask, 'high': ask, 'low': bid, 'close': bid}
        else:
            if self.forming_bar is None:
                self.forming_bar = {'open': ask, 'high': ask, 'low': bid, 'close': bid}
            else:
                self.forming_bar['high'] = max(self.forming_bar['high'], ask)
                self.forming_bar['low'] = min(self.forming_bar['low'], bid)
                self.forming_bar['close'] = bid
        return finalized

    def profit_rub(self, entry, exit_price, lot, direction):
        if direction == 'long':
            diff = exit_price - entry
        else:
            diff = entry - exit_price
        return (diff / self.tick_size) * self.tick_value * lot

    def check_paper_sltp(self, bid, ask):
        if self.position is None or self.position['mode'] != 'paper':
            return None, None
        d = self.position['direction']
        sl, tp = self.position['sl'], self.position['tp']
        if d == 'long':
            if bid <= sl: return sl, "SL"
            if bid >= tp: return tp, "TP"
        else:
            if ask >= sl: return sl, "SL"
            if ask <= tp: return tp, "TP"
        return None, None

    def open_paper(self, direction, ask, bid, now, record_trade_fn):
        if direction == 'long':
            entry, sl, tp = ask, ask - self.sl_dist, ask + self.tp_dist
        else:
            entry, sl, tp = bid, bid + self.sl_dist, bid - self.tp_dist
        self.position = {
            'direction': direction, 'mode': 'paper',
            'entry_price': entry, 'entry_time': now,
            'sl': sl, 'tp': tp, 'lot': self.sim_lot, 'ticket': 0
        }
        print(f"  → [{self.name}] Бумажный {direction.upper()}: "
              f"entry={entry:.{self.digits}f}, SL={sl:.{self.digits}f}, TP={tp:.{self.digits}f}")

    def open_real(self, direction, ask, bid, now, send_order_fn, record_trade_fn):
        lot = self.allocated_lot
        if lot < self.min_real_lot:
            return
        if direction == 'long':
            entry, sl, tp = ask, ask - self.sl_dist, ask + self.tp_dist
        else:
            entry, sl, tp = bid, bid + self.sl_dist, bid - self.tp_dist
        ticket = send_order_fn(self.symbol, direction, lot, sl, tp, self.magic, self.name)
        if ticket is not None:
            self.position = {
                'direction': direction, 'mode': 'real',
                'entry_price': entry, 'entry_time': now,
                'sl': sl, 'tp': tp, 'lot': lot, 'ticket': ticket
            }
            print(f"  → [{self.name}] Реальный {direction.upper()}: "
                  f"entry={entry:.{self.digits}f}, lot={lot:.3f}, ticket={ticket}")

    def close_paper(self, exit_price, reason, now, record_trade_fn):
        if self.position is None:
            return
        p_norm = self.profit_rub(
            self.position['entry_price'], exit_price, self.sim_lot,
            self.position['direction'])
        record_trade_fn(self._trade_dict(exit_price, reason, now, p_norm, p_norm, 'paper'))
        print(f"  → [{self.name}] Закрыт бумажный {self.position['direction'].upper()}: "
              f"{reason}, норм={p_norm:.2f} ₽")
        self.position = None

    def close_real(self, now, close_order_fn, get_deal_exit_price_fn, record_trade_fn):
        if self.position is None:
            return
        ticket = self.position['ticket']
        direction = self.position['direction']
        pos_check = mt5.positions_get(ticket=ticket)
        if not pos_check or len(pos_check) == 0:
            exit_price = get_deal_exit_price_fn(ticket)
            if exit_price is None:
                tick = mt5.symbol_info_tick(self.symbol)
                exit_price = tick.bid if direction == 'long' else tick.ask
            reason = self._guess_exit_reason(exit_price)
        else:
            exit_price = close_order_fn(self.symbol, ticket, direction, self.magic, self.name)
            if exit_price is None:
                return
            reason = "signal"
        p_norm = self.profit_rub(self.position['entry_price'], exit_price, self.sim_lot, direction)
        p_actual = self.profit_rub(self.position['entry_price'], exit_price, self.allocated_lot, direction)
        record_trade_fn(self._trade_dict(exit_price, reason, now, p_norm, p_actual, 'real'))
        print(f"  → [{self.name}] Закрыт реальный {direction.upper()}: "
              f"{reason}, норм={p_norm:.2f} ₽, факт={p_actual:.2f} ₽")
        self.position = None

    def _guess_exit_reason(self, exit_price):
        if exit_price <= self.position['sl'] + self.point:
            return "SL"
        if exit_price >= self.position['tp'] - self.point:
            return "TP"
        return "SL/TP"

    def _trade_dict(self, exit_price, reason, now, p_norm, p_actual, mode):
        return {
            'sc_id': self.sc_id, 'strategy_name': self.name,
            'symbol': self.symbol, 'magic': self.magic,
            'k_period': getattr(self, 'k_period', ''),
            'sl_points': self.sl_points, 'tp_points': self.tp_points,
            'entry_time': self.position['entry_time'], 'exit_time': now,
            'mode': mode, 'direction': self.position['direction'],
            'entry_price': self.position['entry_price'], 'exit_price': exit_price,
            'sl': self.position['sl'], 'tp': self.position['tp'],
            'lot': self.sim_lot if mode == 'paper' else self.allocated_lot,
            'profit_normalized': p_norm, 'profit_actual': p_actual,
            'exit_reason': reason, 'ticket': self.position['ticket']
        }

    def recalc_profit(self, journal_df):
        if journal_df.empty:
            self.window_profit = 0.0
            self.accumulated_profit = 0.0
            return
        my_trades = journal_df[journal_df['sc_id'] == self.sc_id]
        if my_trades.empty:
            self.window_profit = 0.0
            self.accumulated_profit = 0.0
            return
        cutoff = datetime.now() - timedelta(days=self.window_days)
        recent = my_trades[pd.to_datetime(my_trades['exit_time']) >= cutoff]
        self.window_profit = recent['profit_normalized'].sum()
        self.accumulated_profit = my_trades['profit_normalized'].sum()

    def update_mode(self):
        self.mode = "real" if self.window_profit > 0 else "paper"

    def allocate_lot(self, total_window_profit, total_lot):
        if self.window_profit <= 0 or total_window_profit <= 0:
            self.allocated_lot = 0.0
            return
        ratio = self.window_profit / total_window_profit
        self.allocated_lot = round(ratio * total_lot, 2)
        if self.allocated_lot < self.min_real_lot:
            self.allocated_lot = 0.0
