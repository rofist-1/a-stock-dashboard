import pickle, os

cache_dir = 'C:/Users/Rofis/Desktop/百日新高系统/kline_cache'

def check_stock(code, name, target_date):
    fname = code + '.pkl'
    path = os.path.join(cache_dir, fname)
    if not os.path.exists(path):
        print(f'{name} ({code}): K-line file not found')
        return
    with open(path, 'rb') as f:
        data = pickle.load(f)
    df = data['df']
    closes = df['close'].tolist()
    volumes = df['volume'].tolist()
    dates = df['date'].tolist()
    
    # Find the target date index
    try:
        idx = dates.index(target_date)
    except ValueError:
        print(f'{name} ({code}): date {target_date} not found')
        # Show available dates
        print(f'  Available: {dates[-5:]}')
        return
    
    # Get data around that date
    if idx < 60:
        print(f'{name} ({code}): not enough history before {target_date}')
        return
    
    today_c = closes[idx]
    yesterday_c = closes[idx-1]
    change = (today_c - yesterday_c) / yesterday_c * 100
    
    # MA60 at that date
    ma60 = sum(closes[idx-59:idx+1]) / 60
    pct_ma60 = (today_c - ma60) / ma60 * 100
    
    # 60-day low
    low_60 = min(closes[idx-59:idx+1])
    pct_low = (today_c - low_60) / low_60 * 100
    
    # Volume vs MA60
    avg_vol = sum(volumes[idx-59:idx]) / 60
    vol_ratio = volumes[idx] / avg_vol if avg_vol else 0
    
    # Check MA60 direction (compare with 10 days ago)
    ma60_ago = sum(closes[idx-69:idx-9]) / 60 if idx >= 70 else ma60
    ma60_dir = (ma60 - ma60_ago) / ma60_ago * 100 if ma60_ago else 0
    
    # Forward check: what happened 5, 10, 20 days later
    fwd_5 = closes[idx+5] / today_c - 1 if idx+5 < len(closes) else None
    fwd_10 = closes[idx+10] / today_c - 1 if idx+10 < len(closes) else None
    fwd_20 = closes[idx+20] / today_c - 1 if idx+20 < len(closes) else None
    
    print(f'\n=== {name} ({code}) at {target_date} ===')
    print(f'收盘价: {today_c:.2f}')
    print(f'涨幅: {change:+.2f}%')
    print(f'MA60: {ma60:.2f}')
    print(f'距MA60: {pct_ma60:+.1f}%')
    print(f'60日最低: {low_60:.2f}')
    print(f'距60日低点: {pct_low:.1f}%')
    print(f'量比: {vol_ratio:.1f}x')
    print(f'MA60方向(10日变化): {ma60_dir:+.1f}% ({">上升" if ma60_dir > 0.5 else "下降" if ma60_dir < -0.5 else "走平"})')
    print(f'\n后续表现:')
    if fwd_5 is not None: print(f'  5日后: {fwd_5*100:+.1f}%')
    if fwd_10 is not None: print(f'  10日后: {fwd_10*100:+.1f}%')
    if fwd_20 is not None: print(f'  20日后: {fwd_20*100:+.1f}%')

check_stock('sh600010', '北方稀土', '2026-04-29')
check_stock('sz002074', '国轩高科', '2026-04-10')
