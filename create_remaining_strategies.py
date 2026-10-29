# -*- coding: utf-8 -*-
"""Batch generator for remaining 40 strategies."""

import os

BASE = r"C:\Users\UseR\AppData\Roaming\MetaQuotes\Terminal\FA97EA291D4188820508F9D2B5AAD50F\MQL5\Files\PythonProjects\StrategyCloud\strategies"

def write_strategy(name, docstring, idea, entry_cond, exit_cond, diff, calc_code, default=20):
    content = f'''"""{docstring}.

Idea: {idea}
Вход: {entry_cond}
Выход: {exit_cond}
Отличие: {diff}
"""
import numpy as np
import pandas as pd


def calc_{name}(df, period={default}):
    """Расчёт сигнала {name}."""
    {calc_code}
    
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    return (prev == 0 and curr == 1) or (prev == 0 and curr == -1)


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    df = calc_{name}(df, int(param_key))
    
    profit = 0
    n_trades = 0
    trade_profits = []
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        
        for sl in sl_points:
            for tp in tp_points:
                sl_price = df['close'].iloc[i] - sl * spread_points * point
                tp_price = df['close'].iloc[i] + tp * spread_points * point
                
                if prev_k == 0 and curr_k == 1:
                    for j in range(i+1, min(i+50, len(df))):
                        if df['low'].iloc[j] <= sl_price:
                            profit += (sl_price - df['close'].iloc[i]) * sim_lot * tick_value
                            n_trades += 1
                            trade_profits.append(sl_price - df['close'].iloc[i])
                            break
                        elif df['high'].iloc[j] >= tp_price:
                            profit += (tp_price - df['close'].iloc[i]) * sim_lot * tick_value
                            n_trades += 1
                            trade_profits.append(tp_price - df['close'].iloc[i])
                            break
                            
                elif prev_k == 0 and curr_k == -1:
                    sl_price = df['close'].iloc[i] + sl * spread_points * point
                    tp_price = df['close'].iloc[i] - tp * spread_points * point
                    for j in range(i+1, min(i+50, len(df))):
                        if df['high'].iloc[j] >= sl_price:
                            profit += (df['close'].iloc[i] - sl_price) * sim_lot * tick_value
                            n_trades += 1
                            trade_profits.append(df['close'].iloc[i] - sl_price)
                            break
                        elif df['low'].iloc[j] <= tp_price:
                            profit += (df['close'].iloc[i] - tp_price) * sim_lot * tick_value
                            n_trades += 1
                            trade_profits.append(df['close'].iloc[i] - tp_price)
                            break
    
    return (profit, n_trades, trade_profits)
'''
    path = os.path.join(BASE, f"{name}.py")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✓ Created: {name}.py")

# ===== OSCILLATORS (10) =====
write_strategy('osc_fisher_transform',
    'Oscillator: Fisher Transform (H1)',
    '0321 osc_fisher_transform',
    'Fisher > 1.5 and reversal top',
    'Fisher < 0',
    'Fisher transform normalizes oscillators',
    '''
close_norm = (df['close'] - df['low'].rolling(20).min()) / (df['high'].rolling(20).max() - df['low'].rolling(20).min()).replace(0, np.nan)
close_norm = close_norm.clip(-0.999, 0.999)
fisher = 0.5 * np.log((1 + close_norm) / (1 - close_norm))

k = np.zeros(len(df))
k[(fisher > 1.5) & (fisher < fisher.shift(1))] = 1
k[(fisher < -1.5) & (fisher > fisher.shift(1))] = -1
''', 10)

write_strategy('osc_center_of_gravity',
    'Oscillator: Center of Gravity (H1)',
    '0323 osc_center_of_gravity',
    'CG < 0 and rising',
    'CG > 0',
    'DeMark center of gravity oscillator',
    '''
mid = (df['high'] + df['low']) / 2
cg = -(df['close'] - mid).rolling(10).sum() / mid.rolling(10).sum()

k = np.zeros(len(df))
k[(cg < 0) & (cg > cg.shift(1))] = 1
k[(cg > 0) & (cg < cg.shift(1))] = -1
''', 10)

write_strategy('osc_mass_index',
    'Oscillator: Mass Index (H1)',
    '0332 osc_mass_index',
    'Mass Index > 27 then falls',
    '< 26',
    'Reversal detection via high/low range',
    '''
hl_range = np.log(df['high'] / df['low'])
ema1 = hl_range.ewm(span=9).mean()
ema2 = ema1.ewm(span=9).mean()
ratio = ema1 / ema2
mass = ratio.rolling(25).sum()

k = np.zeros(len(df))
k[(mass > 27) & (mass < mass.shift(1))] = 1
k[(mass < 26) & (df['close'] < df['close'].shift(1))] = -1
''', 25)

write_strategy('osc_coppock',
    'Oscillator: Coppock Curve (H1)',
    '0333 osc_coppock',
    'Coppock Curve reversal up',
    'reversal down',
    'Long-term momentum for H1',
    '''
roc14 = df['close'].pct_change(14)
roc11 = roc14.pct_change(11)
coppock = roc11.ewm(span=10).mean()

k = np.zeros(len(df))
k[(coppock > coppock.shift(1)) & (coppock < 0)] = 1
k[(coppock < coppock.shift(1)) & (coppock > 0)] = -1
''', 10)

write_strategy('osc_kst',
    'Oscillator: Know Sure Thing (H1)',
    '0334 osc_kst',
    'KST crosses signal up',
    'down',
    'Sum of ROC weighted by period',
    '''
roc10 = df['close'].pct_change(10)
roc15 = df['close'].pct_change(15)
roc20 = df['close'].pct_change(20)
roc30 = df['close'].pct_change(30)

kst = (roc10 * 1 + roc15 * 2 + roc20 * 3 + roc30 * 4) / 10
signal = kst.rolling(9).mean()

k = np.zeros(len(df))
k[(kst > signal) & (kst.shift(1) <= signal.shift(1))] = 1
k[(kst < signal) & (kst.shift(1) >= signal.shift(1))] = -1
''', 9)

write_strategy('osc_qqe',
    'Oscillator: QQE (H1)',
    '0340 osc_qqe',
    'QQE line crosses 50 up',
    '50 down',
    'Quantitative Qualitative Estimation',
    '''
rsi = pd.Series(50, index=df.index)
rsi[df['close'] > df['close'].shift(1)] = 50 + 50 * (df['close'].diff() / df['high'].rolling(14).max()).clip(0, 1)
qqe = rsi.ewm(span=14).mean()

k = np.zeros(len(df))
k[(qqe > 50) & (qqe.shift(1) <= 50)] = 1
k[(qqe < 50) & (qqe.shift(1) >= 50)] = -1
''', 14)

write_strategy('osc_bop',
    'Oscillator: Balance of Power (H1)',
    '0347 osc_bop',
    'BOP > 0 and rising 3 bars',
    '< 0',
    'Balance of power oscillator',
    '''
hl = df['high'] - df['low']
bop = (df['close'] - df['open']) / hl.replace(0, np.nan)
bop_ema = bop.ewm(span=14).mean()

k = np.zeros(len(df))
k[(bop_ema > 0) & (bop_ema > bop_ema.shift(1)) & (bop_ema > bop_ema.shift(2))] = 1
k[(bop_ema < 0) & (bop_ema < bop_ema.shift(1)) & (bop_ema < bop_ema.shift(2))] = -1
''', 14)

write_strategy('osc_klinger',
    'Oscillator: Klinger Volume Oscillator (H1)',
    '0349 osc_klinger',
    'KVO > 0',
    '< 0',
    'Volume-weighted oscillator',
    '''
roc = df['close'].pct_change(34).abs()
signal = roc.ewm(span=55).mean()
kvo = roc - signal

k = np.zeros(len(df))
k[kvo > 0] = 1
k[kvo < 0] = -1
''', 34)

write_strategy('osc_aroon',
    'Oscillator: Aroon (H1)',
    '0350 osc_aroon_osc',
    'Aroon Oscillator > 50',
    '< 0',
    'Trend vs reversal detection',
    '''
high_25 = df['high'].rolling(25).max()
low_25 = df['low'].rolling(25).min()
aroon_up = (25 - df['high'].rolling(25).apply(lambda x: len(x)-1-x[x==x.max()].index[0], raw=True)) / 25 * 100
aroon_down = (25 - df['low'].rolling(25).apply(lambda x: len(x)-1-x[x==x.min()].index[0], raw=True)) / 25 * 100
osc = aroon_up - aroon_down

k = np.zeros(len(df))
k[osc > 50] = 1
k[osc < 0] = -1
''', 25)

write_strategy('osc_z_rsi',
    'Oscillator: Z-Score RSI (H1)',
    '0354 osc_z_of_rsi',
    'z-score RSI(14) > 2',
    'z < 0',
    'RSI normalized by rolling stats',
    '''
rsi = pd.Series(50, index=df.index)
gains = df['close'].diff().clip(lower=0)
losses = -df['close'].diff().clip(upper=0)
avg_gain = gains.rolling(14).mean()
avg_loss = losses.rolling(14).mean()
rs = avg_gain / avg_loss.replace(0, np.nan)
rsi = 100 - (100 / (1 + rs))

rsi_mean = rsi.rolling(100).mean()
rsi_std = rsi.rolling(100).std()
z = (rsi - rsi_mean) / rsi_std.replace(0, np.nan)

k = np.zeros(len(df))
k[z > 2.0] = 1
k[z < -2.0] = -1
''', 100)

print("\n✓ Created 10 oscillator strategies")
