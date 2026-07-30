# -*- coding: utf-8 -*-
"""
导出策略B(纯60日线+POS)的111笔交易明细为CSV
同时调试：分析亏损交易的共性
"""
import os, sys, pickle, json, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_strategy_comparison import BacktestResult, Trade
import numpy as np

RESULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

# 加载策略B结果
pkl = os.path.join(RESULT_DIR, "result_B.pkl")
with open(pkl, "rb") as f:
    result = pickle.load(f)

trades = result.trades
print(f"策略B: {len(trades)}笔交易")
print(f"总收益: {result.total_return:.2f}%")
print(f"胜率: {result.win_rate:.1f}%")
print(f"盈亏比: {result.profit_loss_ratio:.2f}")

# 排序
st = sorted(trades, key=lambda t: t.buy_date)
wins = [t for t in st if t.pnl_pct > 0]
losses = [t for t in st if t.pnl_pct <= 0]

# 分析亏损原因
print("\n=== 亏损交易分析 ===")
print(f"总亏损: {len(losses)}笔")
print(f"平均亏损: {np.mean([t.pnl_pct for t in losses]):.2f}%")
print(f"中位数亏损: {np.median([t.pnl_pct for t in losses]):.2f}%")
print(f"最大亏损: {min(t.pnl_pct for t in losses):.2f}%")

# 按退出原因统计
from collections import Counter
reasons = Counter(t.exit_reason for t in losses)
print(f"\n退出原因分布(亏损):")
for r, cnt in reasons.most_common():
    avg_pnl = np.mean([t.pnl_pct for t in losses if t.exit_reason == r])
    print(f"  {r}: {cnt}笔, 平均{avg_pnl:.2f}%")

reasons_w = Counter(t.exit_reason for t in wins)
print(f"\n退出原因分布(盈利):")
for r, cnt in reasons_w.most_common():
    avg_pnl = np.mean([t.pnl_pct for t in wins if t.exit_reason == r])
    print(f"  {r}: {cnt}笔, 平均{avg_pnl:.2f}%")

# 按月份统计亏损
monthly_loss = {}
for t in losses:
    m = t.buy_date[:7]
    monthly_loss.setdefault(m, []).append(t.pnl_pct)
print(f"\n亏损按月分布:")
for m in sorted(monthly_loss):
    ts = monthly_loss[m]
    print(f"  {m}: {len(ts)}笔, 平均{np.mean(ts):.2f}%, 合计{sum(ts):.2f}%")

# 亏损集中度：最大几笔占多少
losses_sorted = sorted(losses, key=lambda t: t.pnl_pct)
top5_loss = losses_sorted[:5]
total_loss_sum = sum(t.pnl_pct for t in losses)
top5_sum = sum(t.pnl_pct for t in top5_loss)
print(f"\n前5大亏损占比: {top5_sum:.2f} / {total_loss_sum:.2f} = {abs(top5_sum/total_loss_sum)*100:.1f}%")
for t in top5_loss:
    print(f"  {t.code} {t.name[:8]} {t.buy_date}->{t.sell_date} {t.pnl_pct:.2f}% {t.exit_reason} {t.hold_days}d")

# 持有天数对比
win_days = [t.hold_days for t in wins]
loss_days = [t.hold_days for t in losses]
print(f"\n盈利持仓: 均值{np.mean(win_days):.1f}天, 中位数{np.median(win_days):.0f}天")
print(f"亏损持仓: 均值{np.mean(loss_days):.1f}天, 中位数{np.median(loss_days):.0f}天")

# 止损检查：看亏损交易是否超过了理论止损线
print(f"\n=== 止损执行检查 ===")
# 亏损交易中，看平均亏损是否≥-8%
pct_below_8 = sum(1 for t in losses if t.pnl_pct < -8)
print(f"亏损>-8%: {len(losses)-pct_below_8}笔 ({pct_below_8}笔<-8%)")
avg_pnl_loss = np.mean([t.pnl_pct for t in losses])
print(f"亏损组平均: {avg_pnl_loss:.2f}%")
print(f"→ 如果亏损平均低于-5%，说明止损执行可能有问题")
print(f"→ {'止损执行可能有问题' if avg_pnl_loss < -5 else '止损执行正常'}")

# 导出CSV
csv_path = os.path.join(RESULT_DIR, "strategy_B_trades.csv")
with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["code", "name", "buy_date", "sell_date", "buy_price", "sell_price", 
                 "pnl_pct", "hold_days", "exit_reason", "pnl_amount", "type"])
    for t in st:
        w.writerow([t.code, t.name, t.buy_date, t.sell_date, 
                    round(t.buy_price, 4), round(t.sell_price, 4),
                    round(t.pnl_pct, 2), t.hold_days, t.exit_reason,
                    round(t.pnl_amount, 2), "win" if t.pnl_pct > 0 else "loss"])

print(f"\nCSV导出至: {csv_path}")
print(f"共 {len(trades)} 笔")