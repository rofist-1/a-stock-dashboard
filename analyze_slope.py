import json
# 验证slope5_only的2026实际NAV
with open('results/result_B_slope5_only.json', encoding='utf-8') as f:
    d = json.load(f)
trades = d['trades']
t2026 = [t for t in trades if t['buy_date'].startswith('2026')]

nav_sim = 1.0
for t in t2026:
    impact = t['pnl_pct'] * 0.20 / 100
    nav_sim *= (1 + impact)
print(f"slope5_only 2026:")
print(f"  trades: {len(t2026)}")
print(f"  wins: {len([t for t in t2026 if t['pnl_pct']>0])}")
print(f"  losses: {len([t for t in t2026 if t['pnl_pct']<=0])}")
print(f"  sum_pnl: {sum(t['pnl_pct'] for t in t2026):.1f}%")
print(f"  sim NAV: {nav_sim:.4f} ({(nav_sim-1)*100:.2f}%)")
print(f"  total return: {d['total_return']:.2f}%")
print(f"  max drawdown: {d['max_drawdown']:.2f}%")
print(f"  sharpe: {d['sharpe']:.3f}")

# 对比margin3%+slope5
with open('results/result_B_margin3p_slope5.json', encoding='utf-8') as f:
    d2 = json.load(f)
t2026_2 = [t for t in d2['trades'] if t['buy_date'].startswith('2026')]
nav2 = 1.0
for t in t2026_2:
    nav2 *= (1 + t['pnl_pct'] * 0.20 / 100)
print(f"\nmargin3%+slope5 2026:")
print(f"  sum_pnl: {sum(t['pnl_pct'] for t in t2026_2):.1f}%")
print(f"  sim NAV: {nav2:.4f} ({(nav2-1)*100:.2f}%)")
print(f"  total return: {d2['total_return']:.2f}%")

# 对比margin3%
with open('results/result_B_margin3p.json', encoding='utf-8') as f:
    d3 = json.load(f)
t2026_3 = [t for t in d3['trades'] if t['buy_date'].startswith('2026')]
nav3 = 1.0
for t in t2026_3:
    nav3 *= (1 + t['pnl_pct'] * 0.20 / 100)
print(f"\nmargin3% 2026:")
print(f"  sum_pnl: {sum(t['pnl_pct'] for t in t2026_3):.1f}%")
print(f"  sim NAV: {nav3:.4f} ({(nav3-1)*100:.2f}%)")
print(f"  total return: {d3['total_return']:.2f}%")