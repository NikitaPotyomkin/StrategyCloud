"""Cycle Detection: Spectral Entropy (H1).

Idea: 0739 cyc_spectral_entropy
Вход: спектральная энтропия < p30 (структура/тренд);
      выход когда энтропия > p70 (шум/флэт).
Отличие: спектральная энтропия измеряет упорядоченность частотного состава.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 10-30 баров.
Правка 17.11.2026: энтропия считается по СКОЛЬЗЯЩЕМУ окну (только прошлое).
      Раньше np.fft.fft(close) брали по всему ряду и получали ОДНО число на всю
      историю — энтропия была константой (утечка будущего + сигнал-пустышка).
      Теперь на баре i берём окно [i-win+1 .. i], энтропию и её перцентили
      считаем по прошлому. Первые win-1 баров сигнала не дают (k=0).
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

_MIN_WIN = 32          # окно не меньше 32 баров, иначе спектр бессмысленный
_MAX_WIN = 512         # защита от гигантских окон
_EPS = 1e-12


def _pick_win(period):
    """Размер скользящего окна из параметра стратегии (с ограничениями)."""
    try:
        win = int(period)
    except (TypeError, ValueError):
        win = 128
    return max(_MIN_WIN, min(win, _MAX_WIN))


def _windows(x, win):
    """Матрица скользящих окон (m, win); последняя колонка = текущий бар."""
    try:
        return np.lib.stride_tricks.sliding_window_view(x, win)
    except AttributeError:                      # numpy < 1.20
        m = len(x) - win + 1
        return np.array([x[i:i + win] for i in range(m)])


def _rolling_entropy(x, win):
    """Нормированная спектральная энтропия Шеннона по скользящему окну.

    Возвращает массив длины len(x); в прогреве (первые win-1 баров) — NaN.
    """
    n = len(x)
    out = np.full(n, np.nan)
    if n < win:
        return out

    w = _windows(x, win)
    w = w - w.mean(axis=1, keepdims=True)       # детрендинг по своему окну

    power = np.abs(np.fft.rfft(w * np.hanning(win), axis=1)) ** 2
    power = power[:, 1:]                        # DC-бин отбрасываем
    if power.shape[1] < 2:
        return out

    total = power.sum(axis=1)
    ok = total > _EPS
    prob = np.zeros_like(power)
    prob[ok] = power[ok] / total[ok, None]

    with np.errstate(divide='ignore', invalid='ignore'):
        logp = np.where(prob > 0, np.log(prob), 0.0)
    ent = -np.sum(prob * logp, axis=1)
    ent = ent / np.log(power.shape[1])           # нормировка в [0, 1]

    out[win - 1:] = np.where(ok, ent, np.nan)
    return out


def calc_cyc_spectral_entropy(df, period=128):
    k = np.zeros(len(df))

    win = _pick_win(period)
    if len(df) < win + win:
        df = df.copy()
        df['k'] = k
        return df

    close = df['close'].values.astype(float)
    if not np.all(np.isfinite(close)):
        # только ffill: bfill затянул бы будущее в начало ряда
        close = pd.Series(close).ffill().values

    ent = pd.Series(_rolling_entropy(close, win), index=df.index)

    # Перцентили считаем по ПРОШЛЫМ значениям энтропии (окно заканчивается на i)
    p30 = ent.rolling(win, min_periods=win).quantile(0.30)
    p70 = ent.rolling(win, min_periods=win).quantile(0.70)

    ret = df['close'].pct_change().fillna(0.0)

    # Низкая энтропия = упорядоченная структура: торгуем в сторону бара
    low = ent.notna() & p30.notna() & (ent < p30)
    k[(low & (ret > 0)).values] = 1
    k[(low & (ret < 0)).values] = -1

    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Returns 'long' / 'short' / None for engine run_backtest
    if prev == 0 and curr == 1:
        return 'long'
    if prev == 0 and curr == -1:
        return 'short'
    return None


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    return run_backtest(df, calc_cyc_spectral_entropy, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
