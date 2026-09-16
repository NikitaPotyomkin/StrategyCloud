#функциональные узлы для корректной работы алгоритма
import MetaTrader5 as mt5, time, datetime, pandas as pd
#import PriceAn, Portfolio
import json
import glob
import os
import numpy as np

#акк создан 18 сентября 23г.
# Логин:
# 2000062901
# Пароль трейдера:
# 5jK5ab21j84IVN1E


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


