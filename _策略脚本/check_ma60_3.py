import requests, json, random

apiToken = '4377183a3f71a9eda95741cd2eb8e6a944c6fe90'
base = 'https://api.cxdy.vip/api/'

def get_prefix(code):
    if code.startswith('6') or code.startswith('9'):
        return 'sh'
    return 'sz'

def check_stock(code, name, sig_date):
    symbol = get_prefix(code) + code
    params = {
        'apiToken': apiToken,
        'symbol': symbol,
        'adjust': 'qfq',
        'start_date': '20250101',
        'end_date': '20250630'
    }
    try:
        r = requests.get(base + 'lsjy', params=params, timeout=15)
        rows = r.json()
    except:
        return f'{code}: API error'
    
    if not isinstance(rows, list) or len(rows) < 60:
        return f'{code}: insufficient data ({len(rows) if isinstance(rows, list) else "no data"})'
    
    closes = [float(row['close']) for row in rows]
    dates = [row['date'] for row in rows]
    
    sig_idx = next((i for i, d in enumerate(dates) if d == sig_date), None)
    if sig_idx is None or sig_idx < 60:
        return f'{code}: date {sig_date} not found or idx={sig_idx}'
    
    ma60 = sum(closes[sig_idx-60:sig_idx]) / 60
    close_sig = closes[sig_idx]
    above = close_sig > ma60
    dev = (close_sig / ma60 - 1) * 100
    
    # Check if previously below MA60 within 5 days
    below_count = 0
    for j in range(1, min(6, sig_idx-59)):
        idx = sig_idx - j
        m = sum(closes[idx-60:idx]) / 60
        if closes[idx] < m:
            below_count += 1
    
    return {
        'code': code, 'name': name, 'date': sig_date,
        'close': round(close_sig, 2), 'ma60': round(ma60, 2),
        'dev': round(dev, 2), 'above': above, 'below_5d': below_count
    }

# Sample stocks across dates (with correct exchange codes)
test_stocks = [
    ('600110', '诺德', '2025-06-18'),
    ('300568', '星源', '2025-06-20'),
    ('300990', '同飞', '2025-06-25'),
    ('601886', '旗滨', '2025-06-25'),
    ('301408', '华人', '2025-06-27'),
    ('002278', '神开', '2025-06-26'),
    ('300553', '集智', '2025-06-24'),
    ('600906', '财达', '2025-06-23'),
    ('002797', '一创', '2025-06-24'),
    ('603859', '能科', '2025-06-26'),
    ('002900', '哈三联', '2025-06-27'),
    ('605128', '沪光', '2025-06-27'),
    ('000036', '华联', '2025-06-24'),
    ('002066', '瑞泰', '2025-06-24'),
    ('603005', '晶丰', '2025-06-23'),
    ('002324', '普利', '2025-06-23'),
    ('002527', '新时达', '2025-06-20'),
    ('300842', '帝科', '2025-06-20'),
    ('000541', '佛山', '2025-06-26'),
    ('600522', '中天', '2025-06-26'),
    ('002845', '同兴', '2025-06-16'),
    ('603002', '宏昌', '2025-06-16'),
    ('600054', '黄山', '2025-06-26'),
    ('601567', '三星', '2025-06-26'),
    ('002254', '泰和', '2025-06-25'),
]

for code, name, date in test_stocks:
    result = check_stock(code, name, date)
    if isinstance(result, str):
        print(result)
    else:
        mark = 'OK' if result['above'] else 'FAIL'
        print(f'{result["code"]} {name} ({result["date"]}): close={result["close"]} MA60={result["ma60"]} dev={result["dev"]:+.2f}% {mark} below_5d={result["below_5d"]}/5')
