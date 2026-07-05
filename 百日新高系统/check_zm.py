import pickle, os

cache_dir = 'C:/Users/Rofis/Desktop/百日新高系统/kline_cache'
with open(os.path.join(cache_dir, 'sz301000.pkl'), 'rb') as f:
    kdata = pickle.load(f)

# Data structure is dict with 'date' and 'df' (DataFrame) keys
# DataFrame columns: date, open, close, high, low, volume, amount
df = kdata['df']
closes = df['close'].tolist()
volumes = df['volume'].tolist()
lows = df['low'].tolist()
today_close = closes[-1]
today_vol = volumes[-1]
change = (today_close - closes[-2]) / closes[-2] * 100

# 60-day low
recent_60_low = min(lows[-60:-1]) if len(lows) > 60 else min(lows[:-1])
surge_from_low = (today_close - recent_60_low) / recent_60_low * 100

# Volume vs MA60
avg_vol_60 = sum(volumes[-60:-1]) / 60 if len(volumes) > 60 else sum(volumes[:-1]) / max(len(volumes)-1, 1)
vol_ratio = today_vol / avg_vol_60 if avg_vol_60 else 0

# MA60
ma60 = sum(closes[-60:]) / 60
pct_from_ma60 = (today_close - ma60) / ma60 * 100

print(f'肇民科技 301000')
print(f'今日收盘: {today_close}')
print(f'涨幅: {change:.2f}%')
print(f'60日最低: {recent_60_low}')
print(f'距60日低点: {surge_from_low:.1f}%')
print(f'今日量: {today_vol}')
print(f'60日均量: {avg_vol_60:.0f}')
print(f'量比: {vol_ratio:.1f}x')
print(f'MA60: {ma60:.2f}')
print(f'距MA60: {pct_from_ma60:.1f}%')
print(f'总K线数: {len(kdata)}')
print(f'\n条件检查:')
print(f'  涨幅>7%: {change > 7} ({change:.2f}%)')
print(f'  距低点<30%: {surge_from_low < 30} ({surge_from_low:.1f}%)')
print(f'  放量>1.5x: {vol_ratio >= 1.5} ({vol_ratio:.1f}x)')
