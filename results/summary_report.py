# -*- coding: utf-8 -*-
"""对比: 简化版 vs 策略A vs AGENTS.md预期"""
import os, json, numpy as np

with open(os.path.join("results", "result_simplified.json"), "r", encoding="utf-8") as f:
    sd = json.load(f)

print("=" * 80)
print("简化版 vs 策略A 对比")
print("=" * 80)

# 简化版vs策略A(all 999 stocks)
data = {
    "简化版(站上MA60+量比)": {"trades": 326, "return": -47.01, "wr": 30.1, "pf": 0.67, "dd": 96.85},
    "策略A(百日新高+POS)": {"trades": 83, "return": -35.92, "wr": 21.7, "pf": 2.10, "dd": 42.26},
    "策略B(纯60日线+POS)": {"trades": 111, "return": -4.75, "wr": 33.3, "pf": 2.17, "dd": 26.42},
    "策略C(纯百日新高)": {"trades": 133, "return": -22.64, "wr": 21.8, "pf": 3.19, "dd": 52.33},
}
print(f"{'策略':<30} {'交易':<6} {'收益%':<10} {'胜率%':<8} {'盈亏比':<8} {'回撤%':<8}")
print("-" * 70)
for k, v in data.items():
    print(f"{k:<30} {v['trades']:<6} {v['return']:<+10.2f} {v['wr']:<8.1f} {v['pf']:<8.2f} {v['dd']:<8.2f}")

print("\n" + "=" * 80)
print("5只案例票 三个版本对比")
print("=" * 80)
print(f"{'股票':<20} {'简化版':<10} {'策略A':<10} {'策略B':<10} {'用户预期':<10}")
print("-" * 60)
cases = [
    ("300679电连技术 4/8", "过滤(cross=False)", "过滤(百日新高N)", "过滤(百日新高N)", "入选?(MA60下)"),
    ("301392汇成真空 4/1", "入选(+29.97%)", "过滤(百日新高N)", "过滤(百日新高N)", "入选"),
    ("603083剑桥科技 4/8", "入选(+32.43%)", "过滤(百日新高N)", "过滤(百日新高N)", "入选"),
    ("002259升达林业 1/5", "入选(-3.14%)", "过滤(百日新高N)", "过滤(百日新高N)", "过滤"),
    ("002238天威视讯 2/3", "入选(-0.37%)", "过滤(百日新高N)", "过滤(百日新高N)", "过滤(亏损股)"),
]
for stock, s1, s2, s3, exp in cases:
    print(f"{stock:<20} {s1:<10} {s2:<10} {s3:<10} {exp:<10}")

print("\n" + "=" * 80)
print("简化版核心问题诊断")
print("=" * 80)

# 分析问题
with open(os.path.join("results", "result_simplified.json"), "r", encoding="utf-8") as f:
    d = json.load(f)
ts = d["trades"]
wins = [t for t in ts if t["pnl_pct"] > 0]
losses = [t for t in ts if t["pnl_pct"] <= 0]

print(f"1. 交易频率: {len(ts)}笔/2.5年 = 约{len(ts)//30}笔/月")
print(f"   每日最多5仓, 实际平均持仓{np.mean([t['hold_days'] for t in ts]):.0f}天")
print(f"\n2. 胜率30.1%偏低 — AGENTS.md预期46.6%")
print(f"   - 可能原因: {len(wins)}笔盈利均{wins[0]['pnl_pct'] if wins else 0:.1f}%")
print(f"   - 可能原因: 卖出条件(跌破MA5)在震荡市频繁止损")
print(f"\n3. 盈亏比0.67 (<1.0) — 说明亏损的单笔亏损更大")
print(f"   最佳5笔均收益: {sum(t['pnl_pct'] for t in sorted(ts,key=lambda x:x['pnl_pct'])[-5:])/5:.1f}%")
print(f"   最差5笔均收益: {sum(t['pnl_pct'] for t in sorted(ts,key=lambda x:x['pnl_pct'])[:5])/5:.1f}%")
print(f"\n4. 天威视讯(亏损股)入选 — 缺少FINANCE(30)>0过滤")
print(f"\n5. AGENTS.md原始6月回测(+304%) vs 2.5年回测(-47%)")
print(f"   - 可能是时间窗口差异: 2024年特定6个月行情好")
print(f"   - 也可能是原始回测有未记录的额外过滤条件")