"""Cycle Detection: FFT Dominant Period (H1).

Idea: 0721 cyc_fft_dominant
Вход: доминирующий период FFT(окно) в диапазоне 10-40 баров;
      вход по знаку синусоиды на этом периоде.
Выход: период ушёл из диапазона 10-40 баров.
Отличие: FFT выделяет доминирующий цикл цены.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 10-40 баров.
Правка 17.11.2026: спектр считается по СКОЛЬЗЯЩЕМУ окну (только прошлое).
      Раньше FFT брали по всему ряду — доминирующий период и фаза знали будущее
      (классический lookahead). Теперь на баре i берём окно [i-win+1 .. i],
      период определяем по нему, а фазу — проекцией окна на найденную частоту.
      Первые win-1 баров сигнала не дают (k=0).
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

_MIN_P = 10.0          # нижняя граница интересующих периодов, баров
_MAX_P = 40.0          # верхняя граница, баров
_MIN_WIN = 32          # окно не меньше трёх минимальных периодов
_MAX_WIN = 512         # защита от гигантских окон


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


def _rolling_phase(x, win):
    """Значение подогнанной синусоиды на текущем баре, посчитанное только по прошлым.

    Возвращает массив длины len(x); в прогреве (первые win-1 баров) — NaN.
    """
    n = len(x)
    out = np.full(n, np.nan)
    if n < win:
        return out

    w = _windows(x, win)
    # детрендинг и взвешивание Ханна — по своему окну, ничего из будущего
    w = w - w.mean(axis=1, keepdims=True)
    spec = np.abs(np.fft.rfft(w * np.hanning(win), axis=1))

    freqs = np.fft.rfftfreq(win, d=1.0)
    safe = np.where(freqs > 0, freqs, 1.0)
    periods = np.where(freqs > 0, 1.0 / safe, np.inf)
    mask = (periods >= _MIN_P) & (periods <= _MAX_P)
    if not mask.any():
        return out

    # доминирующий период — по максимуму амплитуды в допустимом диапазоне
    periods_sub = periods[mask]
    dominant = periods_sub[np.argmax(spec[:, mask], axis=1)]

    # фаза: проекция окна на найденную частоту (синус/косинус)
    t = np.arange(win)
    ang = (2.0 * np.pi / dominant)[:, None] * t[None, :]
    a = (2.0 / win) * np.sum(w * np.cos(ang), axis=1)
    b = (2.0 / win) * np.sum(w * np.sin(ang), axis=1)
    # значение синусоиды на последнем баре окна — это и есть «сейчас»
    out[win - 1:] = a * np.cos(ang[:, -1]) + b * np.sin(ang[:, -1])
    return out


def calc_cyc_fft_dominant(df, period=128):
    k = np.zeros(len(df))

    win = _pick_win(period)
    if len(df) < win:
        df = df.copy()
        df['k'] = k
        return df

    close = df['close'].values.astype(float)
    if not np.all(np.isfinite(close)):
        # только ffill: bfill затянул бы будущее в начало ряда
        close = pd.Series(close).ffill().values

    wave = _rolling_phase(close, win)

    valid = np.isfinite(wave)
    k[valid & (wave > 0)] = 1
    k[valid & (wave < 0)] = -1

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
    return run_backtest(df, calc_cyc_fft_dominant, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
