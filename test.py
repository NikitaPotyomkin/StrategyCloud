import datetime, MetaTrader5 as mt5

mt5.initialize()
acc = mt5.account_info()
print('login:', acc.login, '| server:', acc.server, '| name:', acc.name)

tod = datetime.datetime.now() + datetime.timedelta(hours=6)
frm = max(datetime.datetime(2026, 9, 1), tod - datetime.timedelta(days=30))
deals = mt5.history_deals_get(frm, tod) or []
print('deals in window:', len(deals))

ours = [d for d in deals if 770000 <= d.magic <= 869999 and str(d.symbol).endswith('rfd')]
closed = [d for d in ours if d.entry == mt5.DEAL_ENTRY_OUT]
print('ours (magic+rfd):', len(ours), '| closed:', len(closed))
mt5.shutdown()