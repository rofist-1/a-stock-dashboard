import requests, json

apiToken = '4377183a3f71a9eda95741cd2eb8e6a944c6fe90'
base = 'https://api.cxdy.vip/api/'

# Test stocks from different dates
stocks = [
    ('sh600110', '诺德股份', '2025-06-18'),
    ('sh601886', '旗滨集团', '2025-06-25'),
    ('sz301408', '华人健康', '2025-06-27'),
    ('sz002278', '神开股份', '2025-06-26'),
    ('sz300553', '集智股份', '2025-06-24'),
    ('sz300568', '星源材质', '2025-06-20'),
    ('sh600906', '财达证券', '2025-06-23'),
    ('sz002797', '第一创业', '2025-06-24'),
    ('sz300990', '同飞股份', '2025-06-25'),
    ('sh603859', '能科科技', '2025-06-26'),
]

for symbol, name, sig_date in stocks:
    params = {
        'apiToken': apiToken,
        'symbol': symbol,
        'adjust': 'qfq',
        'start_date': '20250101',
        'end_date': '20250630'
    }
    r = requests.get(base + 'lsjy', params=params, timeout=15)
    rows = r.json()
    if not isinstance(rows, list):
        print(f'{name}: unexpected response')
        continue
    
    closes = [float(row['close']) for row in rows]
    dates = [row['date'] for row in rows]
    
    sig_idx = None
    for i, d in enumerate(dates):
        if d == sig_date:
            sig_idx = i
            break
    
    if sig_idx is None or sig_idx < 60:
        print(f'{name}: not enough data (sig_idx={sig_idx}, total={len(rows)})')
        continue
    
    ma60 = sum(closes[sig_idx-60:sig_idx]) / 60
    close_sig = closes[sig_idx]
    above = close_sig > ma60
    
    # Also check prev day
    ma60_prev = sum(closes[sig_idx-61:sig_idx-1]) / 60
    close_prev = closes[sig_idx-1]
    
    result = f'{name} ({symbol}): signal={sig_date} close={close_sig:.2f} MA60={ma60:.2f} dev={(close_sig/ma60-1)*100:+.2f}% ABOVE={above}'
    
    # Previous 5 days check
    days_below = 0
    for j in range(1, 6):
        if sig_idx - j >= 60:
            idx = sig_idx - j
            m = sum(closes[idx-60:idx]) / 60
            if closes[idx] < m:
                days_below += 1
    
    result += f' | prev_close={close_prev:.2f} prev_MA60={ma60_prev:.2f} prev_below={close_prev < ma60_prev}'
    result += f' | 5d_below_count={days_below}/5'
    print(result)
