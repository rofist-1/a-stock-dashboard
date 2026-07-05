import requests, json, sys

apiToken = '4377183a3f71a9eda95741cd2eb8e6a944c6fe90'
base = 'https://api.cxdy.vip/api/'

def check_stock(symbol, name, sig_date):
    params = {
        'apiToken': apiToken,
        'symbol': symbol,
        'adjust': 'qfq',
        'start_date': '20250101',
        'end_date': '20250630'
    }
    r = requests.get(base + 'lsjy', params=params, timeout=15)
    rows = r.json()
    if not isinstance(rows, list) or len(rows) < 60:
        return f'{name}: insufficient data'
    
    closes = [float(row['close']) for row in rows]
    dates = [row['date'] for row in rows]
    
    sig_idx = next((i for i, d in enumerate(dates) if d == sig_date), None)
    if sig_idx is None or sig_idx < 60:
        return f'{name}: signal date not found or insufficient history'
    
    ma60 = sum(closes[sig_idx-60:sig_idx]) / 60
    close_sig = closes[sig_idx]
    above = close_sig > ma60
    
    # 5 days before MA60 check
    below_days = []
    for j in range(1, min(6, sig_idx-59)):
        idx = sig_idx - j
        m = sum(closes[idx-60:idx]) / 60
        if closes[idx] < m:
            below_days.append(f'{dates[idx]}(c={closes[idx]:.2f}<m={m:.2f})')
    
    # Also check if sig date close is close to MA60 (within 2% for borderline)
    dev = (close_sig / ma60 - 1) * 100
    
    return {
        'name': name,
        'symbol': symbol,
        'signal_date': sig_date,
        'close': round(close_sig, 2),
        'ma60': round(ma60, 2),
        'dev_pct': round(dev, 2),
        'above_ma60': above,
        'below_days_count': len(below_days),
        'below_days': below_days[:3],
        'prev_close': round(closes[sig_idx-1], 2),
        'prev_ma60': round(sum(closes[sig_idx-61:sig_idx-1])/60, 2) if sig_idx >= 61 else None
    }

# Check all signal dates in last 10 days
dates_to_check = [
    ('2025-06-16', ['sh300722', 'sh603002', 'sz002845', 'sh688210', 'sz300719', 'sz301012', 'sz301101', 'sz002407', 'sh600121', 'sz002024']),
    ('2025-06-17', ['sh688210', 'sz300722', 'sz300968', 'sz300709', 'sh688257', 'sh688678', 'sz002287', 'sz001205', 'sh688358', 'sz301325', 'sz002225']),
    ('2025-06-20', ['sz300568', 'sz300990', 'sz300271', 'sz300842', 'sz002527', 'sh688502', 'sz301487', 'sz002439', 'sh688699', 'sz300480']),
    ('2025-06-23', ['sh603976', 'sz301101', 'sz300409', 'sz000036', 'sh600906', 'sz300451', 'sz002324', 'sh603005', 'sz002362', 'sz301487']),
    ('2025-06-27', ['sz301408', 'sz002900', 'sh605128', 'sh688625', 'sh688333', 'sh600054']),
]

for sig_date, symbols in dates_to_check:
    print(f'\n=== {sig_date} ===')
    for sym in symbols:
        # Convert to exchange prefix
        if sym.startswith('sh') or sym.startswith('sz'):
            symbol = sym
        else:
            print(f'  {sym}: unknown prefix')
            continue
        
        pref = 'sh' if symbol.startswith('sh') else 'sz'
        code = symbol[2:]
        result = check_stock(symbol, code, sig_date)
        
        if isinstance(result, str):
            print(f'  {code}: {result}')
        else:
            status = '✅' if result['above_ma60'] else '❌'
            print(f'  {code}: close={result["close"]} MA60={result["ma60"]} dev={result["dev_pct"]:+.2f}% {status}')
            if result['below_days_count'] > 0:
                print(f'         5d_below={result["below_days_count"]}/5 ({"; ".join(result["below_days"][:2])})')
            else:
                print(f'         5d_below=0/5 ⚠️ never below MA60 in prior 5 days')
