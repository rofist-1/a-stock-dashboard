# -*- coding: utf-8 -*-
"""
验证 002259 升达林业 1月5日 vs 1月29日
"""
import os, numpy as np, pandas as pd

CACHE_DIR = r"C:\Users\Rofis\Desktop\cache_bt3"
df = pd.read_pickle(os.path.join(CACHE_DIR, "stock_002259.pkl"))

def check_signal(code, name, date_str):
    i = df[df["date"] == date_str].index[0]
    c_arr, h_arr, l_arr, v_arr = df["close"].values, df["high"].values, df["low"].values, df["volume"].values
    cm_arr = df["circ_mv"].values
    
    cp = c_arr[i]; pct = (cp/c_arr[i-1]-1)*100
    new_h = cp >= np.max(c_arr[max(0,i-99):i+1]) if i >= 100 else False
    zt = pct > 9.5; fb = cp >= h_arr[i]
    ma60 = np.mean(c_arr[i-59:i+1]) if i >= 60 else None
    ma60_up = (ma60 > np.mean(c_arr[i-69:i-9])) if i >= 69 else True
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
    amp20=(hh20-ll20)/ll20*100; chg5=(cp/c_arr[i-5]-1)*100 if i>=5 else 0
    cm = cm_arr[i]
    
    pos = a_cls or b_cls or c_cls
    strat_a = new_h and zt and fb and ma60_up and pos and vr>=1.5 and amp20<50 and 20<=cm<=500
    strat_b = zt and fb and ma60_up and pos and vr>=1.5 and 20<=cm<=500
    
    print(f"\n=== {name}({code}) @ {date_str} ===")
    print(f"  收盘: {cp:.2f} (+{pct:.1f}%)")
    print(f"  百日新高: Y={new_h}, HHV(100)={np.max(c_arr[max(0,i-99):i+1]):.2f}")
    print(f"  涨停: Y={zt}, 封板: Y={fb}")
    print(f"  MA60: {ma60:.2f}, MA60方向(上升): Y={ma60_up}, 前10日:{np.mean(c_arr[i-69:i-9]):.2f}")
    print(f"  POS: A={a_cls} B={b_cls} C={c_cls}")
    print(f"  量比: {vr:.1f}x, 20日振幅: {amp20:.1f}%, 5日涨: {chg5:.1f}%, 市值: {cm:.0f}亿")
    print(f"  策略A: {'入选' if strat_a else '过滤'}, 策略B: {'入选' if strat_b else '过滤'}")
    if not strat_a:
        fails = []
        if not new_h: fails.append(f"百日新高(HHV={np.max(c_arr[max(0,i-99):i+1]):.2f})")
        if not zt: fails.append("涨停"); 
        if not fb: fails.append("封板")
        if not ma60_up: fails.append(f"MA60方向(前{np.mean(c_arr[i-69:i-9]):.2f})")
        if not pos: fails.append("POS")
        if vr < 1.5: fails.append(f"量比({vr:.1f}x)")
        if amp20 >= 50: fails.append(f"振幅({amp20:.1f}%)")
        if cm < 20 or cm > 500: fails.append(f"市值({cm:.0f}亿)")
        print(f"  A过滤原因: {', '.join(fails)}")
    return strat_a, strat_b

# 验证1月5日
check_signal("002259", "升达林业", "2026-01-05")
# 验证1月29日
strat_a, _ = check_signal("002259", "升达林业", "2026-01-29")

# 跌停说明：查找后续最大回调
if strat_a:
    i = df[df["date"] == "2026-01-29"].index[0]
    cp = df["close"].iloc[i]
    fwd_high = max(df["high"].iloc[i+1:i+11]) if i+11 < len(df) else cp
    fwd_low = min(df["close"].iloc[i+1:i+21]) if i+21 < len(df) else cp
    print(f"\n  1月29日后10日最高: {fwd_high:.2f} ({(fwd_high/cp-1)*100:.1f}%)")
    print(f"  1月29日后20日最低: {fwd_low:.2f} ({(fwd_low/cp-1)*100:.1f}%)")