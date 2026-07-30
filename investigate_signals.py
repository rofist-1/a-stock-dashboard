# -*- coding: utf-8 -*-
"""
深入核查3只预期入选但实际被过滤的股票
"""
import os, sys
import numpy as np
import pandas as pd

CACHE_DIR = r"C:\Users\Rofis\Desktop\cache_bt3"

def analyze(code, name, target_date):
    df = pd.read_pickle(os.path.join(CACHE_DIR, f"stock_{code}.pkl"))
    c_arr = df["close"].values
    target_idx = df[df["date"] == target_date].index[0]
    
    print(f"\n{'='*70}")
    print(f"{name}({code}) @ {target_date}")
    print(f"{'='*70}")
    
    # 检查100日新高 —— 看前100日哪个价最高
    window_start = max(0, target_idx-99)
    window_end = target_idx + 1
    hhv_100 = np.max(c_arr[window_start:window_end])
    cp = c_arr[target_idx]
    print(f"  当日收盘: {cp:.2f}")
    print(f"  HHV(100): {hhv_100:.2f}")
    print(f"  是否百日新高: {cp >= hhv_100}")
    
    if cp < hhv_100:
        # 找到最高价在哪天
        peak_idx = np.argmax(c_arr[window_start:window_end]) + window_start
        peak_date = df["date"].iloc[peak_idx]
        peak_price = c_arr[peak_idx]
        print(f"  → 最高价出现在: {peak_date} (收盘{peak_price:.2f})")
        print(f"  → 距目标日: {target_idx - peak_idx}天前")
        
        # 检查目标日前100-200日范围，看更高价
        if target_idx >= 200:
            wider_window = c_arr[target_idx-199:target_idx+1]
            hhv_200 = np.max(wider_window)
            peak_idx2 = np.argmax(wider_window) + target_idx - 199
            peak_date2 = df["date"].iloc[peak_idx2]
            if hhv_200 > hhv_100:
                print(f"  → 200日最高价出现在: {peak_date2} (收盘{c_arr[peak_idx2]:.2f})")
        print()
    
    # 查找最近的百日新高日期
    recent_new_highs = []
    for i in range(max(99, target_idx-120), min(target_idx+30, len(c_arr))):
        if c_arr[i] >= np.max(c_arr[max(0,i-99):i+1]):
            d = df["date"].iloc[i]
            recent_new_highs.append((d, c_arr[i]))
    
    if recent_new_highs:
        print(f"  附近(前120~后30日)的百日新高日期:")
        for d, p in recent_new_highs[:10]:
            marking = "*** 目标日 ***" if str(d) == target_date else ""
            print(f"    {d}: {p:.2f} {marking}")
    
    # 检查策略条件的每项
    h_arr, l_arr, v_arr = df["high"].values, df["low"].values, df["volume"].values
    i = target_idx
    
    pct = (c_arr[i]/c_arr[i-1]-1)*100
    ma60 = np.mean(c_arr[i-59:i+1]) if i >= 60 else None
    ma60_up = (ma60 > np.mean(c_arr[i-69:i-9])) if i >= 69 else "N/A"
    a_cls = (c_arr[i-1] < ma60 and cp >= ma60) if (i >= 60 and ma60) else False
    b_cls = (abs(cp/ma60-1) < 0.15) if ma60 else False
    if i >= 9 and ma60:
        ma5, ma10 = np.mean(c_arr[i-4:i+1]), np.mean(c_arr[i-9:i+1])
        b_cls = b_cls and (ma5 > ma10) and (ma10 > np.mean(c_arr[i-12:i-9]))
        days_abv = sum(1 for j in range(max(0,i-4),i+1) if c_arr[j] > np.mean(c_arr[max(0,j-59):j+1]))
        c_cls = (days_abv >= 3 and l_arr[i-1] <= ma60*1.03 and l_arr[i-1] >= ma60*0.97)
    else: c_cls = False
    vol_ma60 = np.mean(v_arr[max(0,i-59):i+1]); vr = v_arr[i]/vol_ma60 if vol_ma60 > 0 else 0
    hh20=np.max(h_arr[max(0,i-19):i+1]); ll20=np.min(l_arr[max(0,i-19):i+1])
    amp20=(hh20-ll20)/ll20*100
    
    print(f"\n  策略条件明细:")
    print(f"    百日新高: {cp>=hhv_100 if i>=100 else 'N/A'}")
    print(f"    涨停: {pct>9.5} (+{pct:.1f}%)")
    print(f"    封板: {cp>=h_arr[i]}")
    print(f"    MA60: {ma60:.2f}, 方向向上: {ma60_up}")
    print(f"    POS-A(蛟龙出海): {a_cls} (前日{c_arr[i-1]:.2f}<MA60={ma60:.2f}<今日{cp:.2f})")
    print(f"    POS-B(均线粘合): {b_cls} (偏离{abs(cp/ma60-1)*100:.1f}%)")
    print(f"    量比: {vr:.1f}x")
    print(f"    20日振幅: {amp20:.1f}%")
    
    strat_a = (i>=100 and cp>=hhv_100) and pct>9.5 and cp>=h_arr[i] and ma60_up and (a_cls or b_cls or c_cls) and vr>=1.5 and amp20<50
    print(f"\n  策略A: {'入选' if strat_a else '过滤'}")

# 检查三只预期入选的票
analyze("300679", "电连技术", "2026-04-08")
analyze("301392", "汇成真空", "2026-04-01")
analyze("603083", "剑桥科技", "2026-04-08")

# 额外检查: 电连技术最近一次真正百日新高
print(f"\n{'='*70}")
print(f"电连技术 2026年百日新高记录")
print(f"{'='*70}")
df = pd.read_pickle(os.path.join(CACHE_DIR, f"stock_300679.pkl"))
c = df["close"].values
for i in range(400, len(c)):
    if c[i] >= np.max(c[max(0,i-99):i+1]):
        d = df["date"].iloc[i]
        print(f"  {d}: {c[i]:.2f}")

# 剑桥科技
print(f"\n{'='*70}")
print(f"剑桥科技 2026年百日新高记录")
print(f"{'='*70}")
df = pd.read_pickle(os.path.join(CACHE_DIR, f"stock_603083.pkl"))
c = df["close"].values
for i in range(400, len(c)):
    if c[i] >= np.max(c[max(0,i-99):i+1]):
        d = df["date"].iloc[i]
        print(f"  {d}: {c[i]:.2f}")

# 汇成真空(次新股,2024-06-05上市)
print(f"\n{'='*70}")
print(f"汇成真空 2025-2026年百日新高记录")
print(f"{'='*70}")
df = pd.read_pickle(os.path.join(CACHE_DIR, f"stock_301392.pkl"))
c = df["close"].values
for i in range(100, len(c)):
    if c[i] >= np.max(c[max(0,i-99):i+1]):
        d = df["date"].iloc[i]
        print(f"  {d}: {c[i]:.2f}")