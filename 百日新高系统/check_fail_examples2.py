import akshare as ak
import pandas as pd

def check_hist(code, name, target_date):
    print(f'\n=== {name} ({code}) at {target_date} ===')
    
    # Fetch historical data around the date
    end_dt = int(target_date[:4]) + 1 if int(target_date[5:7]) >= 10 else target_date[:4]
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", 
                                 start_date="20260101", end_date="20260617",
                                 adjust="qfq")
    except Exception as e:
        print(f'  Failed to fetch: {e}')
        return
    
    # Check if we have enough data
    target = pd.to_datetime(target_date).date() if hasattr(pd, 'to_datetime') else target_date
    try:
        dates = pd.to_datetime(df['日期']).dt.date if hasattr(pd, 'to_datetime') else df['日期']
    except:
        dates = df['日期']
    
    # Find target date
    date_col = '日期'
    df[date_col] = pd.to_datetime(df[date_col])
    
    target_dt = pd.Timestamp(target_date)
    mask = df[date_col] == target_dt
    
    if not mask.any():
        print(f'  Date {target_date} not found in fetched data')
        print(f'  Date range: {df[date_col].min()} ~ {df[date_col].max()}')
        return
    
    idx = df[mask].index[0]
    row = df.loc[idx]
    
    today_c = float(row['收盘'])
    yesterday_c = float(df.loc[idx-1, '收盘'])
    change = (today_c - yesterday_c) / yesterday_c * 100
    
    # MA60
    if idx < 60:
        print(f'  Not enough history ({idx} rows)')
        return
    
    ma60 = df.loc[idx-59:idx, '收盘'].mean()
    pct_ma60 = (today_c - ma60) / ma60 * 100
    
    # 60-day low
    low_60 = df.loc[idx-59:idx, '收盘'].min()
    pct_low = (today_c - low_60) / low_60 * 100
    
    # Volume
    avg_vol_60 = df.loc[idx-59:idx-1, '成交量'].mean()
    vol_ratio = row['成交量'] / avg_vol_60 if avg_vol_60 else 0
    
    # MA60 direction
    ma60_10ago = df.loc[idx-69:idx-10, '收盘'].mean() if idx >= 70 else ma60
    ma60_chg = (ma60 - ma60_10ago) / ma60_10ago * 100 if ma60_10ago else 0
    ma60_dir = '上升' if ma60_chg > 0.5 else ('下降' if ma60_chg < -0.5 else '走平')
    
    # Forward
    fwd_data = {}
    for days, label in [(5, '5日'), (10, '10日'), (20, '20日')]:
        if idx + days < len(df):
            fwd = df.loc[idx+days, '收盘']
            fwd_data[label] = (fwd / today_c - 1) * 100
    
    print(f'  当日涨幅: {change:+.2f}%')
    print(f'  MA60: {ma60:.2f}')
    print(f'  距MA60: {pct_ma60:+.1f}%')
    print(f'  60日最低: {low_60:.2f}')
    print(f'  距60日低点: {pct_low:.1f}%')
    print(f'  量比: {vol_ratio:.1f}x')
    print(f'  MA60方向: {ma60_dir} ({ma60_chg:+.1f}%)')
    for label, val in fwd_data.items():
        print(f'  {label}后: {val:+.1f}%')

check_hist('600010', '北方稀土', '2026-04-29')
check_hist('002074', '国轩高科', '2026-04-10')
