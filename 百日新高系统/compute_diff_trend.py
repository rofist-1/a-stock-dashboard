# -*- coding: utf-8 -*-
"""从K线缓存计算每日 百日新高/百日新低/差值，导出供看板使用"""
import os, json, pickle, time
import pandas as pd
import numpy as np

CACHE = r'C:\Users\Rofis\Desktop\kline_cache'
OUTPUT = os.path.join(os.path.dirname(__file__), '百日新高_差值趋势.json')

START = '2026-01-01'
END   = '2026-06-05'

print("加载K线缓存...")
t0 = time.time()
all_kline = {}
for f in os.listdir(CACHE):
    if not f.endswith('.pkl'): continue
    try:
        with open(os.path.join(CACHE, f), 'rb') as fp:
            data = pickle.load(fp)
        df = data['df']
        all_kline[f.replace('.pkl','')] = df
    except: pass
print(f"  {len(all_kline)} 只, {time.time()-t0:.0f}s")

# 收集所有交易日 (在指定区间内且>100天有数据的)
all_dates = set()
for code, df in all_kline.items():
    for d in df['date'].values:
        if START <= str(d)[:10] <= END:
            all_dates.add(str(d)[:10])
trading_days = sorted(all_dates)
print(f"交易日: {len(trading_days)} 天 ({trading_days[0]} ~ {trading_days[-1]})")

results = []
for di, today in enumerate(trading_days):
    high_count = 0
    low_count = 0
    today_dt = today  # string format
    for code, df in all_kline.items():
        if today_dt not in df['date'].values:
            continue
        row = df[df['date'] == today_dt].iloc[0]
        idx = row.name
        if idx < 100: continue
        window = df.iloc[idx-100:idx+1]
        close = row['close']
        if close >= window['close'].max():
            high_count += 1
        elif close <= window['close'].min():
            low_count += 1
    
    diff = high_count - low_count
    results.append({
        'date': today,
        'high': high_count,
        'low': low_count,
        'diff': diff,
    })
    
    if (di + 1) % 20 == 0 or di == 0 or di == len(trading_days) - 1:
        print(f"  {today}  新高:{high_count}  新低:{low_count}  差值:{diff:+d}")

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False)
print(f"\n导出 {len(results)} 天数据到 {OUTPUT}，耗时 {time.time()-t0:.0f}s")
