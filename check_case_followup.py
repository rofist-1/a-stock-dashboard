# -*- coding: utf-8 -*-
"""补充：检查简化版入选的案例票后续走势"""
import os, numpy as np, pandas as pd

CACHE_DIR = r"C:\Users\Rofis\Desktop\cache_bt3"

def check_trade(code, buy_date_str):
    df = pd.read_pickle(os.path.join(CACHE_DIR, f"stock_{code}.pkl"))
    c = df["close"].values.astype(float); d = df["date"].values
    mask = [str(x)[:10] for x in d]
    if buy_date_str not in mask: return
    i = mask.index(buy_date_str)
    buy_p = c[i] * 1.001 * 1.00025
    print(f"  买入日: {buy_date_str} 买入价: {buy_p:.2f}")
    for k in range(1, min(21, len(c)-i)):
        pnl = (c[i+k] * 1.001 * 1.00025 / buy_p - 1) * 100
        if k <= 5 or k % 5 == 0 or k == 20:
            print(f"    +{k}日: {c[i+k]:.2f} ({pnl:+.2f}%)")
    # 查卖出
    for j in range(i+2, min(i+60, len(c))):
        if j >= 4:
            ma5 = np.mean(c[j-4:j+1])
            if c[j] < ma5:
                sell_p = c[j+1] * 0.999 * 0.9985 if j+1 < len(c) else c[j] * 0.999 * 0.9985
                pnl = (sell_p / buy_p - 1) * 100
                print(f"  卖出: 第{j-i}日, 收益{pnl:+.2f}%")
                return

print("=== 天威视讯(002238) 2026-02-03 入选后走势 ===")
check_trade("002238", "2026-02-04")

print("\n=== 升达林业(002259) 2026-01-05 入选后走势 ===")
check_trade("002259", "2026-01-06")

print("\n=== 汇成真空(301392) 2026-04-01 入选后走势 ===")
check_trade("301392", "2026-04-02")

print("\n=== 剑桥科技(603083) 2026-04-08 入选后走势 ===")
check_trade("603083", "2026-04-09")

print("\n=== 电连技术(300679) 未被选入,查何时站上MA60 ===")
df = pd.read_pickle(os.path.join(CACHE_DIR, "stock_300679.pkl"))
c = df["close"].values.astype(float); d = df["date"].values
for i in range(450, len(c)):
    ma60 = np.mean(c[i-59:i+1]); ma60_prev = np.mean(c[i-60:i])
    if c[i-1] < ma60_prev and c[i] >= ma60:
        print(f"  站上MA60: {str(d[i])[:10]}, 收盘{c[i]:.2f}, MA60:{ma60:.2f}")
        break