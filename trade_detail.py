# -*- coding: utf-8 -*-
"""简化版交易明细导出"""
import os, json

with open(os.path.join("results", "result_simplified.json"), "r", encoding="utf-8") as f:
    data = json.load(f)

trades = data["trades"]
print(f"共 {len(trades)} 笔交易")

# 按代码统计
by_code = {}
for t in trades:
    by_code.setdefault(t["code"], []).append(t)

# 选出交易次数最多的20只
by_code_sorted = sorted(by_code.items(), key=lambda x: len(x[1]), reverse=True)

print("\n交易次数最多的20只票:")
print(f"{'代码':<8} {'名称':<10} {'次数':<6} {'胜率':<8} {'总收益%':<10}")
for code, ts in by_code_sorted[:20]:
    w = sum(1 for t in ts if t["pnl_pct"] > 0)
    total = sum(t["pnl_pct"] for t in ts)
    name = ts[0]["name"][:8] if len(ts[0]["name"]) > 8 else ts[0]["name"]
    print(f"{code:<8} {name:<10} {len(ts):<6} {w/len(ts)*100:.0f}%{'':<4} {total:<+10.1f}")

# 最好/最差交易
by_pnl = sorted(trades, key=lambda t: t["pnl_pct"])
print(f"\n最佳5笔:")
for t in by_pnl[-5:][::-1]:
    print(f"  {t['code']} {t['name'][:6]:<6} {t['buy_date']}->{t['sell_date']} {t['pnl_pct']:+7.2f}% {t['hold_days']}d")

print(f"\n最差5笔:")
for t in by_pnl[:5]:
    print(f"  {t['code']} {t['name'][:6]:<6} {t['buy_date']}->{t['sell_date']} {t['pnl_pct']:+7.2f}% {t['hold_days']}d")

# 分月统计
by_month = {}
for t in trades:
    ym = t["buy_date"][:7]
    by_month.setdefault(ym, []).append(t)

print(f"\n月胜率分布 (前15):")
for ym in sorted(by_month)[:15]:
    ts = by_month[ym]
    w = sum(1 for t in ts if t["pnl_pct"] > 0)
    ret = sum(t["pnl_pct"] for t in ts)
    print(f"  {ym}: {len(ts):3d}笔 胜率{w/len(ts)*100:.0f}% 合计{ret:+7.1f}%")