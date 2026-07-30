import json

# 计算实际组合收益 vs 合计pnl_pct
for ver, label in [("result_B_base.json", "原版B"), 
                    ("result_B_index_filter.json", "大盘过滤"),
                    ("result_B_full.json", "大盘+竞价止损")]:
    with open(f'results/{ver}', encoding='utf-8') as f:
        d = json.load(f)
    trades = d['trades']
    total_return = d['total_return']
    
    # 分年度sum_pnl
    years = {}
    for t in trades:
        y = t['buy_date'][:4]
        years.setdefault(y, {"trades": 0, "sum_pnl": 0, "wins": 0, "losses": 0})
        years[y]["trades"] += 1
        years[y]["sum_pnl"] += t['pnl_pct']
        if t['pnl_pct'] > 0:
            years[y]["wins"] += 1
        else:
            years[y]["losses"] += 1
    
    print(f"\n=== {label}: 总收益{total_return:.2f}% ===")
    for y in sorted(years.keys()):
        v = years[y]
        print(f"  {y}: {v['trades']}笔, W{v['wins']}L{v['losses']}, 合计pnl_pct={v['sum_pnl']:.1f}%")
    
    # 计算2026实际NAV变化 - 用简单复利模拟
    # 每个交易等权重(20%/笔)，同时最多5笔
    # 逐个交易累加净值
    nav = 1.0
    for t in trades:
        if t['buy_date'].startswith('2026'):
            # 按20%仓位模拟
            impact = t['pnl_pct'] * 0.20 / 100
            nav *= (1 + impact)
    
    print(f"  2026模拟NAV: {nav:.4f} ({(nav-1)*100:.2f}%)")
    
    # 看实际组合层面的2026 NAV
    if 'nav' in d and d['nav']:
        nav_data = d['nav']
        for i, n in enumerate(nav_data):
            if n[0].startswith('2026-01-01'):
                start_nav = n[1]
                break
        for n in reversed(nav_data):
            if n[0].startswith('2026'):
                end_nav = n[1]
                break
        print(f"  2026 NAV: {start_nav:.4f} → {end_nav:.4f} ({(end_nav/start_nav-1)*100:.2f}%)")