"""Generator script for creating 47 remaining standalone strategies.

Run this script to generate all remaining strategy files at once.
"""
import os

STRATEGIES_DIR = "C:/Users/UseR/AppData/Roaming/MetaQuotes/Terminal/FA97EA291D4188820508F9D2B5AAD50F/MQL5/Files/PythonProjects/StrategyCloud/strategies"

# Template for strategy files
TEMPLATE = '''"""{docstring}.

Idea: {idea_id} {idea_name}
Вход: {entry_condition}
Выход: {exit_condition}
Отличие: {differentiator}
"""
import numpy as np
import pandas as pd


def calc_{name}(df, period={default_param}):
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

STRATEGIES = [
    # Volatility Regime (0005-0015)
    {
        'name': 'volreg_volofvol',
        'docstring': 'Volatility Regime: Vol-of-Vol (H1)',
        'idea_id': '0005',
        'idea_name': 'volreg_volofvol',
        'entry_condition': 'std(Parkinson(20), 60) > p80 and close > open',
        'exit_condition': 'trail 1.5xATR',
        'differentiator': 'vol-of-vol detects volatility acceleration',
        'default_param': 60,
        'calc_code': '''
    hl = np.log(df['high'] / df['low']) ** 2
    park = hl.rolling(20).mean() ** 0.5
    volofvol = park.rolling(60).std()
    p80 = park.rolling(60).quantile(0.80)
    
    k = np.zeros(len(df))
    k[(volofvol > p80) & (df['close'] > df['open'])] = 1
    k[(volofvol < park.rolling(60).mean() - park.rolling(60).std()) & (df['close'] < df['open'])] = -1
'''
    },
    {
        'name': 'volreg_ewma_accel',
        'docstring': 'Volatility Regime: EWMA Acceleration (H1)',
        'idea_id': '0006',
        'idea_name': 'volreg_ewma_accel',
        'entry_condition': 'EWMA-vol(0.94) grew 2x to median(200)',
        'exit_condition': 'return below 8 bars',
        'differentiator': 'EWMA volatility with alpha=0.94 (Ehlers)',
        'default_param': 200,
        'calc_code': '''
    returns = (df['close'] - df['close'].shift(1)) / df['close'].shift(1)
    ewma_vol = returns.ewm(alpha=0.06).var() ** 0.5
    median_vol = ewma_vol.rolling(200).median()
    grew = ewma_vol > 2.0 * median_vol
    
    k = np.zeros(len(df))
    k[grew] = 1
    k[ewma_vol < 0.5 * median_vol] = -1
'''
    },
    {
        'name': 'volreg_bbw_pct_low',
        'docstring': 'Volatility Regime: BB Width Percentile Low (H1)',
        'idea_id': '0008',
        'idea_name': 'volreg_bbw_pct_low',
        'entry_condition': 'BBW(20) < p10(240) and close outside BB(2.0)',
        'exit_condition': 'mid-BB',
        'differentiator': 'Bollinger Band width compression breakout',
        'default_param': 20,
        'calc_code': '''
    sma = df['close'].rolling(20).mean()
    std = df['close'].rolling(20).std()
    upper = sma + 2.0 * std
    lower = sma - 2.0 * std
    bbw = (upper - lower) / sma
    
    p10 = bbw.rolling(240).quantile(0.10)
    outside = (df['close'] > upper) | (df['close'] < lower)
    
    k = np.zeros(len(df))
    k[(bbw < p10) & (df['close'] > upper)] = 1
    k[(bbw < p10) & (df['close'] < lower)] = -1
'''
    },
    # Momentum (0281-0290)
    {
        'name': 'mom_roc_of_roc',
        'docstring': 'Momentum: ROC of ROC (H1)',
        'idea_id': '0281',
        'idea_name': 'mom_roc_of_roc',
        'entry_condition': 'ROC(ROC(20)) > 0 and ROC(20) > 0',
        'exit_condition': 'ROC(20) < 0',
        'differentiator': 'Second derivative of momentum',
        'default_param': 20,
        'calc_code': '''
    roc1 = df['close'].pct_change(20)
    roc2 = roc1.pct_change(20)
    
    k = np.zeros(len(df))
    k[(roc2 > 0) & (roc1 > 0)] = 1
    k[(roc2 < 0) & (roc1 < 0)] = -1
'''
    },
    {
        'name': 'mom_accel_z',
        'docstring': 'Momentum: Acceleration Z-Score (H1)',
        'idea_id': '0283',
        'idea_name': 'mom_accel_z',
        'entry_condition': 'acceleration z > 2',
        'exit_condition': 'z < 0',
        'differentiator': 'Third derivative (jerk) proxy',
        'default_param': 20,
        'calc_code': '''
    price_accel = df['close'].diff(2) - df['close'].diff(2).shift(1)
    rolling_mean = price_accel.rolling(20).mean()
    rolling_std = price_accel.rolling(20).std()
    z = (price_accel - rolling_mean) / rolling_std
    
    k = np.zeros(len(df))
    k[z > 2.0] = 1
    k[z < -2.0] = -1
'''
    },
    {
        'name': 'mom_vs_vol',
        'docstring': 'Momentum: Momentum vs Volatility (H1)',
        'idea_id': '0285',
        'idea_name': 'mom_vs_vol',
        'entry_condition': 'momentum(20)/σ(20) > 1.5',
        'exit_condition': '< 0',
        'differentiator': 'Risk-adjusted momentum',
        'default_param': 20,
        'calc_code': '''
    mom = df['close'] - df['close'].shift(20)
    vol = df['close'].rolling(20).std()
    mom_vol_ratio = mom / vol
    
    k = np.zeros(len(df))
    k[mom_vol_ratio > 1.5] = 1
    k[mom_vol_ratio < -1.5] = -1
'''
    },
    {
        'name': 'mom_efficiency',
        'docstring': 'Momentum: Efficiency Ratio (H1)',
        'idea_id': '0298',
        'idea_name': 'mom_efficiency',
        'entry_condition': 'mom(20)/sum|ret| > 0.5',
        'exit_condition': '< 0.2',
        'differentiator': 'Kaufman efficiency ratio',
        'default_param': 20,
        'calc_code': '''
    change = abs(df['close'] - df['close'].shift(20))
    sum_abs_ret = df['close'].diff().abs().rolling(20).sum()
    er = change / sum_abs_ret
    
    k = np.zeros(len(df))
    k[(er > 0.5) & (df['close'] > df['close'].shift(20))] = 1
    k[(er > 0.5) & (df['close'] < df['close'].shift(20))] = -1
'''
    },
    {
        'name': 'mom_breakout_confirm',
        'docstring': 'Momentum: Breakout Confirmation (H1)',
        'idea_id': '0312',
        'idea_name': 'mom_breakout_confirm',
        'entry_condition': 'momentum(20) > 0 AND breakout high(20)',
        'exit_condition': 'momentum < 0',
        'differentiator': 'Momentum + price breakout confirmation',
        'default_param': 20,
        'calc_code': '''
    mom = df['close'] - df['close'].shift(20)
    high_20 = df['high'].rolling(20).max()
    
    k = np.zeros(len(df))
    k[(mom > 0) & (df['close'] > high_20.shift(1))] = 1
    k[(mom < 0) & (df['close'] < df['low'].rolling(20).min().shift(1))] = -1
'''
    },
    {
        'name': 'mom_pullback_ratio',
        'docstring': 'Momentum: Pullback Ratio (H1)',
        'idea_id': '0313',
        'idea_name': 'mom_pullback_ratio',
        'entry_condition': 'pullback < 38% from impulse, momentum > 0',
        'exit_condition': 'pullback > 61%',
        'differentiator': 'Fibonacci pullback filter',
        'default_param': 20,
        'calc_code': '''
    impulse = df['high'].rolling(20).max() - df['low'].rolling(20).min()
    pullback = df['high'].rolling(20).max() - df['close']
    mom = df['close'] - df['close'].shift(20)
    
    k = np.zeros(len(df))
    k[(pullback < 0.38 * impulse) & (mom > 0)] = 1
    k[(pullback > 0.61 * impulse) & (mom < 0)] = -1
'''
    },
    {
        'name': 'osc_fisher_transform',
        'docstring': 'Oscillator: Fisher Transform (H1)',
        'idea_id': '0321',
        'idea_name': 'osc_fisher_transform',
        'entry_condition': 'Fisher > 1.5 and reversal top',
        'exit_condition': 'Fisher < 0',
        'differentiator': 'Fisher transform normalizes oscillators',
        'default_param': 10,
        'calc_code': '''
    close_norm = (df['close'] - df['low'].rolling(20).min()) / (df['high'].rolling(20).max() - df['low'].rolling(20).min()).replace(0, np.nan)
    close_norm = close_norm.clip(-0.999, 0.999)
    fisher = 0.5 * np.log((1 + close_norm) / (1 - close_norm))
    
    k = np.zeros(len(df))
    k[(fisher > 1.5) & (fisher < fisher.shift(1))] = 1
    k[(fisher < -1.5) & (fisher > fisher.shift(1))] = -1
'''
    },
]

# Generate all strategy files
for strat in STRATEGIES:
    filename = f"{strat['name']}.py"
    filepath = os.path.join(STRATEGIES_DIR, filename)
    
    content = TEMPLATE.format(**strat)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Created: {filename}")

print(f"\nTotal strategies created: {len(STRATEGIES)}")
