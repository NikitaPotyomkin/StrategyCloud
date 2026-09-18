#функциональные узлы для корректной работы алгоритма
import MetaTrader5 as mt5, time, datetime, pandas as pd
#import PriceAn, Portfolio
import json
import glob
import os
import csv
import numpy as np
from itertools import product

#акк создан 18 сентября 23г.
# Логин:
# 2000062901
# Пароль трейдера:

# functions.py — добавить к остальным функциям

# ⬅ НОВОЕ: пишем активные стратегии для дэшборда
def write_active_state(active, active_strategies, balance, max_risk_pct, journal_dir):
    """Сохраняет текущее состояние активных стратегий для Streamlit-дэшборда."""
    import json
    state = {
        'updated': datetime.now().isoformat(),
        'balance': balance,
        'quota': balance * max_risk_pct,
        'total_strategies': len(active),
        'strategies': []
    }
    for r in active:
        key = strategy_key(r)
        strat = active_strategies.get(key, {})
        has_position = strat.get('position') is not None
        state['strategies'].append({
            'symbol': r['symbol'],
            'type': r.get('type', 'stoch'),
            'k_period': r.get('k_period', '-'),
            'sl_points': r.get('sl_points', '-'),
            'tp_points': r.get('tp_points', '-'),
            'parabolic_step': r.get('parabolic_step', '-'),
            'parabolic_max': r.get('parabolic_max', '-'),
            'score': r['score'],
            'lot': r['lot'],
            'profit': r.get('profit', 0),
            'profit_factor': r.get('profit_factor', 0),
            'win_rate': r.get('win_rate', 0),
            'n_trades': r.get('n_trades', 0),
            'has_position': has_position,
        })
    path = os.path.join(journal_dir, 'active_state.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def distribute_lots(ranked_results, symbol_data, balance,
                    max_risk_pct=0.05, min_lot=0.01, min_score=0.8):
    """⬅ добавлен параметр min_score"""
    quota = balance * max_risk_pct

    candidates = []
    for r in ranked_results:
        if r['score'] < min_score:          # ⬅ НОВОЕ: порог
            continue
        if r['score'] <= 0:
            continue
        info = symbol_data[r['symbol']]['info']
        sl_money = (r['sl_points'] * info.point
                    * info.trade_tick_value / info.trade_tick_size)
        if sl_money <= 0:
            continue
        candidates.append({**r, 'sl_money': sl_money})

    if not candidates:
        return []

    # Дальше всё как было — жадный отбор, распределение лотов
    active = []
    for c in candidates:
        trial = active + [c]
        denom = sum(x['sl_money'] * x['score'] for x in trial)
        if denom == 0:
            continue
        lot = quota * c['score'] / denom
        if lot < min_lot:
            break
        active.append(c)

    denom = sum(x['sl_money'] * x['score'] for x in active)
    for x in active:
        x['lot'] = round(quota * x['score'] / denom, 2)
        if x['lot'] < min_lot:
            x['lot'] = min_lot

    return active



def _short_name(r):
    pair = get_non_usd(r['symbol'])
    stype = r.get('type', 'stoch')
    if stype == 'parabolic':
        return f"{pair}/SAR s{r['k_period']}"
    return f"{pair}/Stoch K{r['k_period']}"


def deduplicate_results(results):
    """Удаляет стратегии с одинаковым результатом (SL/TP не срабатывает)."""
    seen = set()
    unique = []
    for r in results:
        # Ключ: символ + K + профит + n_trades (если они одинаковые — стратегия идентична)
        key = (r['symbol'], r['k_period'], r['profit'], r['n_trades'])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def calc_metrics(trade_profits):
    """
    Считает метрики по списку профитов сделок.
    Возвращает dict с метриками.
    """
    if not trade_profits or len(trade_profits) == 0:
        return {
            'profit': 0, 'n_trades': 0, 'profit_factor': 0,
            'max_drawdown': 0, 'win_rate': 0, 'sharpe': 0,
            'avg_trade': 0, 'recovery': 0
        }

    profits = np.array(trade_profits)
    total_profit = profits.sum()
    n = len(profits)

    # Profit Factor
    gross_profit = profits[profits > 0].sum()
    gross_loss = abs(profits[profits < 0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0

    # Max Drawdown (по кривой equity)
    equity = np.cumsum(profits)
    running_max = np.maximum.accumulate(equity)
    drawdowns = running_max - equity
    max_drawdown = drawdowns.max() if len(drawdowns) > 0 else 0

    # Win Rate
    win_rate = (profits > 0).sum() / n * 100

    # Sharpe (упрощённый, без risk-free rate)
    if profits.std() > 0:
        sharpe = profits.mean() / profits.std()
    else:
        sharpe = 0

    # Avg Trade
    avg_trade = total_profit / n

    # Recovery Factor
    recovery = total_profit / max_drawdown if max_drawdown > 0 else 999.0

    return {
        'profit': total_profit,
        'n_trades': n,
        'profit_factor': profit_factor,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'sharpe': sharpe,
        'avg_trade': avg_trade,
        'recovery': recovery
    }


def composite_score(metrics, weights=None):
    """
    Композитный скор на основе взвешенной суммы метрик.

    Веса по умолчанию:
      profit       — 0.35  (главный драйвер)
      profit_factor— 0.25  (качество прибыли)
      win_rate     — 0.15  (стабильность)
      sharpe       — 0.15  (ровность кривой)
      recovery     — 0.10  (восстановление после просадки)

    Метрики нормируются, чтобы ни одна не доминировала.
    """
    if weights is None:
        weights = {
            'profit': 0.35,
            'profit_factor': 0.25,
            'win_rate': 0.15,
            'sharpe': 0.15,
            'recovery': 0.10
        }

    # Нормировка: приводим к сопоставимому масштабу
    # profit — делим на 1000 (типичный профит 500–1500)
    # profit_factor — делим на 2 (хороший PF ~2)
    # win_rate — делим на 100 (0–100%)
    # sharpe — оставляем как есть (обычно 0.1–3.0)
    # recovery — делим на 5 (хороший recovery ~5)

    normalized = {
        'profit': metrics['profit'] / 1000,
        'profit_factor': min(metrics['profit_factor'], 5) / 2,  # кап на 5, иначе PF=999 всё убьёт
        'win_rate': metrics['win_rate'] / 100,
        'sharpe': max(min(metrics['sharpe'], 3), -3) / 3,  # кап от -3 до 3
        'recovery': min(metrics['recovery'], 10) / 5  # кап на 10
    }

    score = sum(weights[k] * normalized[k] for k in weights)
    return score

def get_non_usd(symbol):
    pair = symbol[:-3]  # убираем rfd
    base, quote = pair[:3], pair[3:]
    return base if base != "USD" else quote

def get_last_file(path): #получить последний файл
    list_of_files = glob.glob(path) # * means all if need specific format then *.csv
    latest_file = max(list_of_files, key=os.path.getctime)
    return latest_file

def curr_time(): #функция определения текущего времени
    now = datetime.datetime.now()
    return (now.strftime("%H:%M"))

def get_weekday(): #получить день недели
    weekday = datetime.datetime.today().weekday()
    return weekday

def get_time_item(item_num):
    #получает элементы сегодняшней даты поэлементно (год месяц дни часы минуты)
    year, month, day, hour, min = map(int, time.strftime("%Y %m %d %H %M").split())
    items = [year,month,day,hour,min]
    return items[item_num]

def write_to_log_file(text):
    #записывать все сообщения в лог файл
    with open('analytics\\log_file.txt', 'w') as f:
        if isinstance(text,str): f.write(text + '\n')
        if isinstance(text,list):
            for x in text:
                f.write(x+'\n')

def terminal_on (acc):
    print(f"Подключаемся к аккаунту: {acc}")
    # установим подключение к терминалу MetaTrader 5
    i,limit,interval = 0,5,150
    while i<limit:
        accounts_credentials = {'demo':[2000066590, "3cm%3dxbZx", "AlfaForexRU-Real"]}
                                #'real':[1100041193, "tverCity69X", "AlfaForexRU-Real"]}
        #Alpari: login=51231575, server="Alpari-MT5-Demo", password="9XY7da8Q6"
        # login, password, server = 51231575,"9XY7da8Q6","Alpari-MT5-Demo"
        #login, password, server = 2000045513, "tMfp67JFQS", "AlfaForexRU-Real"
        try:
            creds = accounts_credentials[acc]
            print(f'Попытка подключения: {creds}')
        except KeyError:
            print('Указанный счет не найден!')
        login, password, server = creds[0],creds[1],creds[2]
        if not mt5.initialize(login=login, server=server, password=password):
            print("initialize() failed, error code =", mt5.last_error())
            i+=1
            msg = f'{curr_time()} попытка подключения {i}'
            print(msg)
            time.sleep(interval*2)
            if i == limit-1: quit()
        else:
            print(f"Подключение к счету {accounts_credentials[acc][0]}: успешно")
            i=limit
def get_equity(): #получить данные о текущем портфеле
    account_info = mt5.account_info()
    if account_info != None:
        # выведем данные о торговом счете в виде словаря
        account_info_dict = mt5.account_info()._asdict()
        # преобразуем словарь в DataFrame и выведем на печать
        df = pd.DataFrame(list(account_info_dict.items()), columns=['property', 'value'])
        balance = df["value"].iloc[10]
        # equity = df["value"].iloc[13]
        msg = f'баланс: {balance}'
    else:
        msg = 'Нет данных о счете!' #оповещаем, что нет данных о счете
    return msg

def determine_parameters(order_open_pos, symbol):
    if order_open_pos == mt5.ORDER_TYPE_BUY:
        close_price = mt5.symbol_info_tick(symbol).ask
        order_close_pos = mt5.ORDER_TYPE_SELL

    if order_open_pos == mt5.ORDER_TYPE_SELL:
        close_price = mt5.symbol_info_tick(symbol).bid
        order_close_pos = mt5.ORDER_TYPE_BUY

    #calculating sl and tp
    if order_open_pos == mt5.ORDER_TYPE_BUY:
        price = mt5.symbol_info_tick(symbol).bid

    if order_open_pos == mt5.ORDER_TYPE_SELL:
        price = mt5.symbol_info_tick(symbol).ask

    return close_price,order_close_pos,price

def send_order(lot,order_open_pos,symbol,price,basis): #формирует ордер на открытие
    now = datetime.datetime.now().strftime('%H:%M')
    print(f'{now} открытие ордера {symbol}, {lot} lot')
    deviation = 12
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_open_pos,
        "price": price,
        "deviation": deviation,
        "magic": 234000,
        "comment": basis,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    # отправим торговый запрос
    i = 0
    while i <1:
        result = mt5.order_send(request)
        time.sleep(1)
        i =+1
    return result

def close_order(lot,type,symbol,close_price,ticket): #формирует ордер на закрытие
    if type =='mt5.ORDER_TYPE_SELL': type = mt5.ORDER_TYPE_SELL
    elif type == 'mt5.ORDER_TYPE_BUY': type = mt5.ORDER_TYPE_BUY
    lot = float(lot)
    msg = f'закрытие позиции: {symbol} {str(lot)} лот'
    send_telegram(msg,True)
    price = close_price
    deviation = 15
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": type,
        "price": price,
        "deviation": deviation,
        "magic": 234000,
        "position": ticket,
        "comment": "closing",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK
    }
    #отправим торговый запрос
    i,result = 0,None
    while result == None or 'No prices' in str(result):
        result = mt5.order_send(request)
        time.sleep(1)
        i = +1
        if i ==10:
            print(f'{curr_time()}: не получается закрыть тикет {ticket}. Проверьте кнопку разрешения торговли в терминале!')
            break
    return result

def create_order(symbol,order_type, lot, basis, adv_id,spread): #инициирует создание ордера на сделку
    if order_type == mt5.ORDER_TYPE_SELL:
        msg = f'{curr_time()} {symbol} перекуплен в зоне {basis}, продаем (спред {spread})'
        send_telegram(msg,True)
    if order_type == mt5.ORDER_TYPE_BUY:
        msg = f'{curr_time()} {symbol} перепродан в зоне {basis}, покупаем (спред {spread})'
        send_telegram(msg, True)
    order_open_pos = order_type
    values = determine_parameters(order_open_pos, symbol)
    result = send_order(lot, order_open_pos, symbol, values[2],'p'+str(adv_id)+" " + basis)
    if result is None:
        print ('      ошибка открытия ордера')
    else:
        print('      ticket: ' + str(result.order))

def calc_lot(equity_percentage):
    account_info_dict = mt5.account_info()._asdict()
    df = pd.DataFrame(list(account_info_dict.items()), columns=['property', 'value'])
    balance = df["value"].iloc[10]
    lot = round((balance * equity_percentage / 100) / 1000, 2)
    return lot

def check_close_status (type, symbol,op, pct_50,curr_price,volume,ticket):
    action,h = '', get_time_item(3)
    if symbol == 'USDJPY' in symbol:
        delta = 0.015
    else:
        delta = 0.00015

    if h<23:
        op,pct_50 = op[symbol],pct_50[symbol]['p50']
        if type == 0:
            target_finres = round(op - pct_50, 5)-delta
            if curr_price > target_finres:
                action = f"{str(ticket)} {symbol} SELL {volume} BY MARKET"
            else: action = "HOLD"
        elif type == 1:
            target_finres = round(op + pct_50, 5)+delta #+DELTA
            if curr_price < target_finres:
                action = f"{str(ticket)} {symbol} BUY {volume} BY MARKET"
            else: action = "HOLD"
    elif h>=23:
        if type == 0: action = f"{str(ticket)} {symbol} SELL {volume} BY MARKET"
        elif type == 1:action = f"{str(ticket)} {symbol} BUY {volume} BY MARKET"
    return action

def check_spread(symbol,bid,ask,spread_lims): #проверяет размер спреда
    spread_x = 1000
    if 'JPY' in symbol: spread_x,round_x = 1000,3
    else: spread_x,round_x = spread_x*100,5
    spread = int(round(float(ask)-float(bid),round_x)*spread_x)
    lim = spread_lims[symbol]
    if spread<=lim:flag = True
    else:flag = False
    return flag, spread

def split_volume(lot):
    t = get_time_item(3)
    part_lot = round((float(lot) / (24 - int(t))), 2)
    return part_lot

def rec_unrs_profit(time,profit):
    with open("detected_profits.txt",'a') as f:
        substr = str(time)+','+str(profit)+'\n'
        f.write(substr)
    f.close()

def show_start_msgs(advisor_id,now):
    print(f'Запускаем алгоритм... Проверьте кнопку разрешения торговли в терминале')
    msg = f'Advisor ID = {advisor_id}. Время запуска (мск.время): ' + now.strftime("%d-%m-%Y %H:%M")
    send_telegram(msg,True)


# def get_daily_limits (symbols):
#     print('Определяем параметры на день по каждому инструменту (диапазон, цену открытия)')
#     missing,pct, op = [],{}, {} # pct - процентили интервала цен, op - цена открытия
#     with open(get_last_file(r"daily limits\*"),'r') as f:
#         lines = f.readlines()
#     pct = ast.literal_eval(lines[0])
#     i = 0
#     open_price_received = 'no'
#     while open_price_received!='yes':
#         for symbol in symbols:  # получим дневные лимиты для каждого символа
#             try:
#                 day_parameters = PriceAn.get_day_limits(symbol)
#             except IndexError:
#                 if get_weekday() in [5,6]:
#                     print('Выходной день, рынок закрыт.')#проверить на соответствие тайм зон (иначе поломается тебе в пятницу в 9 вечера)
#                     quit()
#                 print(f'{symbol}: отсутствует история цен')
#                 missing.append(symbol)
#             op[symbol] = round(day_parameters[1], 5)  # получим цену открытия символа сегодня в 00:00
#         if missing==False:
#             open_price_received = 'no'
#             i+=1
#             time.sleep(5)
#         else:
#             open_price_received = 'yes'
#         if i>10:
#             print('ошибка получения цен: останавливаем работу программы')
#             quit()
#         #print(f'{symbol} Цена откр.: {op[symbol]}, процентили: {pct[symbol]}')
#     return pct,op,missing

# def adv_percent_portfolio_research (pct, op):
#     port, close_f = Portfolio.show_curr_pos(), False  # изучаем структуру портфеля
#     if isinstance(port, str) == False:  # если df портфеля пустая, то вернётся стринг значение
#         port['action'] = port.apply(lambda x: check_close_status(x['type'], x['symbol'],
#                                                           op, pct, x['price_current'],
#                                                                  x['volume'], x['ticket']),
#                                     axis=1)  # создадим новую колонку с данными
#         #если в портфеле содержатся команды на закрытие, то обозначим это во флаге
#         if port['action'].str.contains("BUY", case=False).any() == True:  close_f =True
#         if port['action'].str.contains("SELL", case=False).any() == True: close_f =True
#     return port,close_f

def alg_stoch_portfolio_research(): #анализ портфеля на закрытие для алгоритма стохастика
    pass

def send_telegram(text: str, display_in_terminal: bool):
    if display_in_terminal ==True: print(text)
    try:
        token = "5463006761:AAHtkpDczyJhwbgiInkxhIaE_4DPtR3BqyQ"
        url = "https://api.telegram.org/bot"
        channel_id = "-1001772302469"
        url += token
        method = url + "/sendMessage"

        try:
            # r = requests.post(method, data={
            #      "chat_id": channel_id,
            #      "text": text
            #       })
            print('отправляем сообщение в тг (заглушка)')
        except:
            print(f"{curr_time()} post_text error!")

        # if r.status_code != 200:
        #     print("post_text error")
    except:
        print('tg error')

def find_lot_size():
    #размер лота определяется вручную, для прибыльных валют чуть выше
    lot_d = {}
    with open(("trade_instructions\lot_size.txt"),'r') as f:
        lines = f.readlines()
        i = 0
        for line in lines:
            if i>0:
                line = line.replace('\n','').split(',')
                symbol,lot = line[0],float(line[1])
                lot_d[symbol] = lot
            i+=1
    return lot_d

from datetime import date
def update_lims(d):
    td = str(date.today())
    if td in d:
        return True
    else:
        print(f"{curr_time()} Обновление ценовых параметров")
        return False

def calc_close_delta (value,symbol):
    if symbol =='USDJPYrfd': delta = value/1000
    else: delta = value/100000
    return delta

# def update_percentiles():
#     td = str(date.today())
#     now = datetime.datetime.now()
#     day_parameters = []
#
#     # определяем набор торгуемых символов
#     symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD']
#     symbols = [x + 'rfd' for x in symbols]  # у Альфы постфикс rfd
#     pct = {} # pct - процентили интервала цен, op - цена открытия
#     for symbol in symbols:  # получим дневные лимиты для каждого символа
#         try:
#             day_parameters = PriceAn.get_day_limits(symbol)
#         except IndexError:
#             print(f'{symbol}: отсутствует история цен')
#         pct[symbol] = day_parameters[2]  # занесем в словарь с percentiles данные по символу p50, p75, p95
#         #print(f'{symbol} Цена откр.: {op[symbol]}, процентили: {pct[symbol]}')
#         #запишем лимиты в файл
#     with open(rf"C:\Users\Никита\Dropbox\PycharmProjects\MT5 FX Technologies\daily limits\{td}.txt","w") as f:
#         f.write(json.dumps(pct))
#     print(f'{now.strftime("%H:%M")} дневные лимиты сохранены в файл {td}.txt')
#
# def observe_market(symbols):
#     #вернуть разницу - сколько сейчас отклонение, и сколько триггер для открытия рынка
#     text = 'this is market analysis'
#     return 'Market'

#send_telegram('тест',True)


# ═══ КЛЮЧИ СТРАТЕГИЙ ═══
def strategy_key(symbol, param, stype='stoch', extra=None):
    if stype == 'parabolic' and extra is not None:
        return f"{symbol}_{stype}_S{param}_M{extra}"
    return f"{symbol}_{stype}_K{param}"


def make_magic(symbol, stype, param, extra=None):
    """Детерминированный magic-номер на основе параметров стратегии."""
    raw = f"{symbol}_{stype}_{param}_{extra}"
    h = 0
    for ch in raw:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return 770000 + (h % 100000)


def send_order(symbol, direction, lot, sl, tp, magic, comment, symbol_data):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    if direction == 'long':
        order_type, price = mt5.ORDER_TYPE_BUY, tick.ask
    else:
        order_type, price = mt5.ORDER_TYPE_SELL, tick.bid
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": lot,
        "type": order_type, "price": price, "sl": sl, "tp": tp,
        "deviation": 20, "comment": comment, "magic": magic,
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_FOK
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        request["type_filling"] = mt5.ORDER_FILLING_IOC
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"  → Ордер не прошёл: {result.retcode}, {result.comment}")
            return None
    print(f"  → {direction.upper()} {symbol}: ticket={result.order}, "
          f"price={price:.{symbol_data[symbol]['info'].digits}f}, lot={lot:.2f}, comment={comment}")
    return result.order


def close_order(symbol, ticket, direction, magic, symbol_data):
    pos_info = mt5.positions_get(ticket=ticket)
    if not pos_info:
        return None
    pos = pos_info[0]
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    if direction == 'long':
        close_type, price = mt5.ORDER_TYPE_SELL, tick.bid
    else:
        close_type, price = mt5.ORDER_TYPE_BUY, tick.ask
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": pos.volume,
        "position": ticket, "type": close_type, "price": price,
        "deviation": 20, "comment": "close", "magic": magic,
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_FOK
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        request["type_filling"] = mt5.ORDER_FILLING_IOC
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"  → Закрытие не прошло: {result.retcode}, {result.comment}")
            return None
    print(f"  → Закрыт {symbol} ticket={ticket}, price={price:.{symbol_data[symbol]['info'].digits}f}")
    return price


def get_deal_exit_price(ticket):
    deals = mt5.history_deals_get(datetime.datetime.now() - datetime.timedelta(hours=48), datetime.datetime.now())
    if deals:
        for d in sorted(deals, key=lambda x: x.time, reverse=True):
            if d.position_id == ticket and d.entry == mt5.DEAL_ENTRY_OUT:
                return d.price
    return None


def _record_close(key, s, now, exit_price, reason, symbol_data, record_trade_fn):
    """Общая логика записи закрытия сделки в журнал. Возвращает profit."""
    info = symbol_data[s['symbol']]['info']
    tick_val = info.trade_tick_value
    tick_size = info.trade_tick_size
    diff = (exit_price - s['position']['entry_price']) if s['position']['direction'] == 'long' \
        else (s['position']['entry_price'] - exit_price)
    profit = (diff / tick_size) * tick_val * s['position']['lot']
    record_trade_fn({
        'symbol': s['symbol'], 'k_period': s['k_period'],
        'sl_points': s['sl_points'], 'tp_points': s['tp_points'],
        'entry_time': s['position']['entry_time'], 'exit_time': now,
        'direction': s['position']['direction'],
        'entry_price': s['position']['entry_price'],
        'exit_price': exit_price, 'lot': s['position']['lot'],
        'profit': profit, 'exit_reason': reason, 'ticket': s['position']['ticket']
    }, None, None)
    print(f"  → [{key}] Закрыт ({reason}): profit={profit:.2f}")
    s['position'] = None
    return profit


def write_ranking(top_strats, all_results, JOURNAL_DIR, BACKTEST_DAYS, TOP_N, LOT_PER_STRATEGY):
    # --- CSV ---
    csv_file = os.path.join(JOURNAL_DIR, "rankings.csv")
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['rank', 'symbol', 'type', 'k_period', 'parabolic_max',
                         'sl_points', 'tp_points',
                         'profit', 'pf', 'mdd', 'win_rate', 'sharpe',
                         'recovery', 'score', 'top'])
        for i, r in enumerate(all_results):
            is_active = any(
                s['symbol'] == r['symbol'] and s['k_period'] == r['k_period']
                and s['sl_points'] == r['sl_points'] and s['tp_points'] == r['tp_points']
                and s.get('type', 'stoch') == r.get('type', 'stoch')
                and s.get('parabolic_max') == r.get('parabolic_max')
                for s in top_strats
            )
            pair = r['symbol'].replace('rfd', '')
            stype = r.get('type', 'stoch')
            pmax = r.get('parabolic_max')
            pmax_str = f"{pmax:.2f}" if pmax is not None else ""
            writer.writerow([i+1, pair, stype, r['k_period'], pmax_str,
                             r['sl_points'], r['tp_points'],
                             round(r['profit'], 2), round(r['profit_factor'], 2),
                             round(r['max_drawdown'], 2), round(r['win_rate'], 1),
                             round(r['sharpe'], 2), round(r['recovery'], 1),
                             round(r['score'], 3), "TOP" if is_active else ""])

    # --- TXT ---
    txt_file = os.path.join(JOURNAL_DIR, "ranking.txt")
    lines = [
        "=" * 120,
        f"  RANKING | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Окно бэктеста: {BACKTEST_DAYS} дней | Всего комбинаций: {len(all_results)}",
        "=" * 120,
        (f"  {'#':<4} {'Symbol':<12} {'Type':<8} {'K/Step':>6} {'Max':>5} {'SL':>5} {'TP':>5} "
         f"{'Profit':>10} {'PF':>6} {'MDD':>8} {'WinR':>6} {'Sharpe':>7} {'Recov':>6} "
         f"{'Score':>7} {'Top':>6}"),
        "-" * 120
    ]

    for i, r in enumerate(all_results):
        is_active_txt = "▶ TOP" if any(
            s['symbol'] == r['symbol'] and s['k_period'] == r['k_period']
            and s['sl_points'] == r['sl_points'] and s['tp_points'] == r['tp_points']
            and s.get('type', 'stoch') == r.get('type', 'stoch')
            and s.get('parabolic_max') == r.get('parabolic_max')
            for s in top_strats
        ) else ""
        stype = r.get('type', 'stoch')
        k_or_step = r['k_period']
        pmax = r.get('parabolic_max')
        pmax_str = f"{pmax:.2f}" if pmax is not None else ""
        lines.append(
            f"  {i+1:<4} {r['symbol']:<12} {stype:<8} {k_or_step:>6} {pmax_str:>5} "
            f"{r['sl_points']:>5} {r['tp_points']:>5} "
            f"{r['profit']:>+9.1f} {r['profit_factor']:>5.2f} {r['max_drawdown']:>+7.1f} "
            f"{r['win_rate']:>5.1f}% {r['sharpe']:>6.2f} {r['recovery']:>5.1f} "
            f"{r['score']:>6.3f} {is_active_txt:>6}"
        )

    lines += [
        "-" * 120,
        f"  Топ-{TOP_N} активны на демо, лот={LOT_PER_STRATEGY} на каждую",
        "=" * 120
    ]

    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def sync_active_strategies(top_results, now, symbol_data, active_strategies, close_order_fn, get_deal_exit_price_fn,
                           record_trade_fn, strategy_key_fn, make_magic_fn, MAGIC_BASE, TOP_N):
    """Открывает позиции для новых топ-N, закрывает те, что выпали из топа."""
    # Текущие ключи топа
    top_keys = set()
    for r in top_results:
        stype = r.get('type', 'stoch')
        param = r['k_period']
        extra = r.get('parabolic_max')
        top_keys.add(strategy_key_fn(r['symbol'], param, stype, extra))

    # Закрываем те, что выпали из топа
    to_close = [key for key in active_strategies if key not in top_keys]

    for key in to_close:
        s = active_strategies[key]
        if s['position'] is not None:
            exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                        s['position']['direction'], s['magic'], symbol_data)
            if exit_price is not None:
                tick_val = symbol_data[s['symbol']]['info'].trade_tick_value
                tick_size = symbol_data[s['symbol']]['info'].trade_tick_size
                diff = (exit_price - s['position']['entry_price']) if s['position']['direction'] == 'long' \
                    else (s['position']['entry_price'] - exit_price)
                profit = (diff / tick_size) * tick_val * s['position']['lot']
                record_trade_fn({
                    'symbol': s['symbol'], 'k_period': s['k_period'],
                    'sl_points': s['sl_points'], 'tp_points': s['tp_points'],
                    'entry_time': s['position']['entry_time'], 'exit_time': now,
                    'direction': s['position']['direction'],
                    'entry_price': s['position']['entry_price'],
                    'exit_price': exit_price, 'lot': s['position']['lot'],
                    'profit': profit, 'exit_reason': 'rerank', 'ticket': s['position']['ticket']
                }, None, None)
                print(f"  → [{key}] Закрыт (вышел из топа): profit={profit:.2f}")
            s['position'] = None
        del active_strategies[key]

    # Добавляем новые из топа
    for r in top_results:
        stype = r.get('type', 'stoch')
        param = r['k_period']
        extra = r.get('parabolic_max')
        key = strategy_key_fn(r['symbol'], param, stype, extra)
        if key not in active_strategies:
            active_strategies[key] = {
                'symbol': r['symbol'],
                'k_period': param,
                'parabolic_max': r.get('parabolic_max', 0.2),
                'sl_points': r['sl_points'],
                'tp_points': r['tp_points'],
                'type': stype,
                'magic': make_magic_fn(r['symbol'], stype, param, extra),
                'position': None,
            }
            print(f"  → [{key}] Добавлен в топ-{TOP_N}")

    # Проверяем реальные позиции (могли закрыться по SL/TP у брокера)
    for key, s in active_strategies.items():
        if s['position'] is not None:
            pos_check = mt5.positions_get(ticket=s['position']['ticket'])
            if not pos_check:
                exit_price = get_deal_exit_price_fn(s['position']['ticket'])
                if exit_price is None:
                    tick = mt5.symbol_info_tick(s['symbol'])
                    exit_price = tick.bid if s['position']['direction'] == 'long' else tick.ask
                tick_val = symbol_data[s['symbol']]['info'].trade_tick_value
                tick_size = symbol_data[s['symbol']]['info'].trade_tick_size
                diff = (exit_price - s['position']['entry_price']) if s['position']['direction'] == 'long' \
                    else (s['position']['entry_price'] - exit_price)
                profit = (diff / tick_size) * tick_val * s['position']['lot']
                record_trade_fn({
                    'symbol': s['symbol'], 'k_period': s['k_period'],
                    'sl_points': s['sl_points'], 'tp_points': s['tp_points'],
                    'entry_time': s['position']['entry_time'], 'exit_time': now,
                    'direction': s['position']['direction'],
                    'entry_price': s['position']['entry_price'],
                    'exit_price': exit_price, 'lot': s['position']['lot'],
                    'profit': profit, 'exit_reason': 'SL/TP', 'ticket': s['position']['ticket']
                }, None, None)
                print(f"  → [{key}] Закрыт брокером (SL/TP): profit={profit:.2f}")
                s['position'] = None


def check_active_signals(now, active_strategies, symbol_data, calc_stochastic_fn, check_exit_stoch_fn,
                         check_entry_stoch_fn, calc_parabolic_fn, check_exit_parabolic_fn,
                         check_entry_parabolic_fn, send_order_fn, close_order_fn, get_deal_exit_price_fn,
                         _record_close_fn, LOT_PER_STRATEGY, record_trade_fn):
    """Проверяет сигналы для активных стратегий на закрытом баре."""
    for key, s in active_strategies.items():
        if s['symbol'] not in symbol_data:
            continue
        sd = symbol_data[s['symbol']]
        df = sd['df_h1']

        stype = s.get('type', 'stoch')
        info = sd['info']
        digits = info.digits

        if stype == 'stoch':
            df = calc_stochastic_fn(df, s['k_period'])
            if len(df) < 2:
                continue

            prev_k = df['k'].iloc[-2]
            last_k = df['k'].iloc[-1]

            # ── Если есть позиция — проверяем выход ──
            if s['position'] is not None:
                pos_check = mt5.positions_get(ticket=s['position']['ticket'])
                if not pos_check:
                    exit_price = get_deal_exit_price_fn(s['position']['ticket'])
                    if exit_price is None:
                        tick = mt5.symbol_info_tick(s['symbol'])
                        exit_price = tick.bid if s['position']['direction'] == 'long' else tick.ask
                    _record_close_fn(key, s, now, exit_price, 'SL/TP', symbol_data, record_trade_fn)
                    continue

                if check_exit_stoch_fn(prev_k, last_k, s['position']['direction']):
                    exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                s['position']['direction'], s['magic'], symbol_data)
                    if exit_price is not None:
                        _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn)

            # ── Если нет позиции — проверяем вход ──
            if s['position'] is None:
                entry_dir = check_entry_stoch_fn(prev_k, last_k)
                if entry_dir:
                    tick = mt5.symbol_info_tick(s['symbol'])
                    if tick is None:
                        continue
                    sl_dist = s['sl_points'] * info.point
                    tp_dist = s['tp_points'] * info.point
                    if entry_dir == 'long':
                        entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                    else:
                        entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist

                    comment = f"{s['symbol']}, K={s['k_period']}"
                    ticket = send_order_fn(s['symbol'], entry_dir, LOT_PER_STRATEGY,
                                           sl, tp, s['magic'], comment, symbol_data)
                    if ticket is not None:
                        s['position'] = {
                            'direction': entry_dir,
                            'entry_price': entry,
                            'entry_time': now,
                            'ticket': ticket,
                            'lot': LOT_PER_STRATEGY,
                        }
                        print(f"  → [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}")

        elif stype == 'parabolic':
            df = calc_parabolic_fn(df, s['k_period'], s.get('parabolic_max', 0.2))
            if len(df) < 2:
                continue

            prev_sar = df['sar'].iloc[-2]
            current_sar = df['sar'].iloc[-1]
            prev_close = df['close'].iloc[-2]
            current_close = df['close'].iloc[-1]

            # ── Если есть позиция — проверяем выход ──
            if s['position'] is not None:
                pos_check = mt5.positions_get(ticket=s['position']['ticket'])
                if not pos_check:
                    exit_price = get_deal_exit_price_fn(s['position']['ticket'])
                    if exit_price is None:
                        tick = mt5.symbol_info_tick(s['symbol'])
                        exit_price = tick.bid if s['position']['direction'] == 'long' else tick.ask
                    _record_close_fn(key, s, now, exit_price, 'SL/TP', symbol_data, record_trade_fn)
                    continue

                if check_exit_parabolic_fn(prev_sar, current_sar, prev_close, current_close,
                                           s['position']['direction']):
                    exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                s['position']['direction'], s['magic'], symbol_data)
                    if exit_price is not None:
                        _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn)

            # ── Если нет позиции — проверяем вход ──
            if s['position'] is None:
                entry_dir = check_entry_parabolic_fn(prev_sar, current_sar, prev_close, current_close)
                if entry_dir:
                    tick = mt5.symbol_info_tick(s['symbol'])
                    if tick is None:
                        continue
                    sl_dist = s['sl_points'] * info.point
                    tp_dist = s['tp_points'] * info.point
                    if entry_dir == 'long':
                        entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                    else:
                        entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist

                    comment = f"{s['symbol']}, Step={s['k_period']}, Max={s.get('parabolic_max', 0.2)}"
                    ticket = send_order_fn(s['symbol'], entry_dir, LOT_PER_STRATEGY,
                                           sl, tp, s['magic'], comment, symbol_data)
                    if ticket is not None:
                        s['position'] = {
                            'direction': entry_dir,
                            'entry_price': entry,
                            'entry_time': now,
                            'ticket': ticket,
                            'lot': LOT_PER_STRATEGY,
                        }
                        print(f"  → [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}")


def run_full_backtest(SYMBOLS, symbol_data, K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST,
                      PARABOLIC_STEPS, PARABOLIC_MAXS, BACKTEST_DAYS, TOP_N,
                      backtest_stoch, backtest_parabolic, calc_metrics, composite_score, deduplicate_results):
    """Перебирает все комбинации стохастика и параболика. Возвращает (top, all)."""
    all_results = []
    total_symbols = len(SYMBOLS)
    global_start = time.time()

    # Предрасчёт размеров
    stoch_per_symbol = len(K_PERIODS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    parab_per_symbol = len(PARABOLIC_STEPS) * len(PARABOLIC_MAXS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    combos_per_symbol = stoch_per_symbol + parab_per_symbol
    total_combos = combos_per_symbol * total_symbols

    print(f"  Всего комбинаций: ~{total_combos} ({stoch_per_symbol} stoch + {parab_per_symbol} parab на символ)")

    sym_idx = 0
    for symbol in SYMBOLS:
        if symbol not in symbol_data:
            continue
        sd = symbol_data[symbol]
        info = sd['info']
        df_window = sd['df_h1'].tail(BACKTEST_DAYS * 24)
        if len(df_window) < 30:
            continue

        sym_idx += 1
        sym_start = time.time()
        combos_done = 0
        print(f"\n  [{sym_idx}/{total_symbols}] {symbol} — {len(df_window)} баров H1")

        # ── Стохастик ──
        stoch_mark = max(1, stoch_per_symbol // 5)
        for i, (k, sl, tp) in enumerate(product(K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST), start=1):
            profit, n_trades, trade_profits = backtest_stoch(
                df_window, k, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            all_results.append({
                'symbol': symbol, 'type': 'stoch', 'k_period': k,
                'parabolic_max': None,
                'sl_points': sl, 'tp_points': tp,
                'profit': profit, 'n_trades': n_trades,
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'sharpe': metrics['sharpe'],
                'recovery': metrics['recovery'],
                'score': score,
            })
            combos_done += 1
            if i % stoch_mark == 0 or i == stoch_per_symbol:
                pct = 100 * combos_done / combos_per_symbol
                print(f"    Stoch {i}/{stoch_per_symbol}  |  общий прогресс {pct:.0f}%")

        # ── Параболик ──
        parab_mark = max(1, parab_per_symbol // 5)
        for i, (step, max_val, sl, tp) in enumerate(
            product(PARABOLIC_STEPS, PARABOLIC_MAXS, SL_POINTS_LIST, TP_POINTS_LIST),
            start=1
        ):
            profit, n_trades, trade_profits = backtest_parabolic(
                df_window, step, max_val, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            all_results.append({
                'symbol': symbol, 'type': 'parabolic', 'k_period': step,
                'parabolic_max': max_val,
                'sl_points': sl, 'tp_points': tp,
                'profit': profit, 'n_trades': n_trades,
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'sharpe': metrics['sharpe'],
                'recovery': metrics['recovery'],
                'score': score,
            })
            combos_done += 1
            if i % parab_mark == 0 or i == parab_per_symbol:
                pct = 100 * combos_done / combos_per_symbol
                print(f"    Parab  {i}/{parab_per_symbol}  |  общий прогресс {pct:.0f}%")

        sym_elapsed = time.time() - sym_start
        total_elapsed = time.time() - global_start
        print(f"    {symbol} готов: {combos_done} комб. за {sym_elapsed:.1f}с"
              f"  |  всего {len(all_results)} комб. за {total_elapsed:.1f}с")

    # ── Дедупликация и сортировка ──
    print(f"\n  Дедупликация {len(all_results)} результатов...")
    all_results = deduplicate_results(all_results)
    all_results.sort(key=lambda x: x['score'], reverse=True)

    # Лучшая стратегия для каждого символа
    seen_symbols = set()
    top_results = []
    for r in all_results:
        if r['symbol'] not in seen_symbols:
            top_results.append(r)
            seen_symbols.add(r['symbol'])
        if len(top_results) >= TOP_N:
            break

    total_elapsed = time.time() - global_start
    print(f"  Бэктест завершён: {len(all_results)} комб. за {total_elapsed:.1f}с")

    return top_results, all_results
