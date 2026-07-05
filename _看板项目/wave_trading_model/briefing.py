# -*- coding: utf-8 -*-
"""
每日简报生成模块
===============
"""

from datetime import datetime

# avoid relative import failures
import importlib, sys, os
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)
import config
from market_state import analyze_market
from market_style import analyze_style
from sector_analysis import get_mainline_sectors, analyze_sectors
from stock_screener import screen_all_mainline_dragons, screen_all_mainline_trend_leaders
from data_fetcher import fetch_market_stats


def generate_briefing(index_code=config.INDEX_CODE, sector_limit=config.SECTOR_TOP_N,
                      stock_limit=config.STOCK_WATCH_N, monitor=False, new_high_data=None,
                      new_low=0):
    """
    new_high_data: [(板块名称, 百日新高总数, 今日新增, "hot"|"watch"), ...]
    new_low: 全市场百日新低数
    """
    market_state = analyze_market(index_code)
    market_style = analyze_style()
    all_sectors = analyze_sectors(limit=20, new_high_data=new_high_data)
    mainlines = get_mainline_sectors(limit=sector_limit, new_high_data=new_high_data)

    # 情绪龙头（原逻辑，保留作为市场情绪信号灯）
    sentiment_dragons = screen_all_mainline_dragons(mainlines, limit_per_sector=stock_limit)

    # 趋势中军（新增，只做前3个最强板块）
    trend_leaders = screen_all_mainline_trend_leaders(mainlines, top_k=3)

    buy_signals = []
    if monitor:
        for sector in trend_leaders:
            for d in sector.get("trend_leaders", []):
                if d.get("qualified"):
                    buy_signals.append(d)
        if buy_signals:
            from buy_point import monitor_dragon_list
            buy_signals = monitor_dragon_list(buy_signals[:5])

    briefing = {
        "title": "波段交易模型 \xb7 每日决策简报",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market_state": market_state,
        "market_style": market_style,
        "mainline_sectors": {
            "count": len(mainlines),
            "list": mainlines,
        },
        "all_sectors": all_sectors,
        "sentiment_dragons": sentiment_dragons,
        "trend_leaders": trend_leaders,
        "buy_point_alerts": _classify_signals(buy_signals),
        "action_summary": _generate_action_summary(market_state, market_style,
                                                    mainlines, trend_leaders, buy_signals),
        "config": {
            "rps_threshold": config.RPS_THRESHOLD_LEADER,
            "rps_warn": config.RPS_WARN_THRESHOLD,
            "launch_volume_shrink": config.LAUNCH_VOLUME_SHRINK,
            "relay_volume_shrink": config.RELAY_VOLUME_SHRINK,
            "relay_min_gain": f"{config.RELAY_MIN_GAIN*100:.0f}%",
            "max_positions": config.MAX_POSITIONS,
            "trend_leader_min_cap": f">{config.TREND_LEADER_MIN_CIRC_MARKET_YI}亿",
            "trend_leader_min_amt": f">{config.TREND_LEADER_MIN_AMOUNT_5D_YI}亿",
        },
        "market_stats": fetch_market_stats(new_low=new_low),
    }
    return briefing


def _classify_signals(signals):
    return {
        "buy_signals": [s for s in signals if s.get("triggered") and "\u4e70\u70b9" in s.get("signal_type", "")],
        "exit_signals": [s for s in signals if s.get("triggered") and "\u5356\u51fa" in s.get("signal", "")],
        "strong_watch": [s for s in signals if not s.get("triggered") and s.get("zone") == "\u5f3a\u52bf\u89c2\u5bdf\u533a"],
        "neutral": [s for s in signals if s not in ("buy", "exit", "watch")],
    }


def _generate_action_summary(market_state, market_style, mainlines, trend_leaders, signals):
    state = market_state["state"]
    position_text = market_state["position_limit_text"]
    style = market_style["style"]
    buy_sigs = [s for s in signals if s.get("triggered") and "\u4e70\u70b9" in s.get("signal_type", "")]
    exit_sigs = [s for s in signals if s.get("triggered") and "\u5356\u51fa" in s.get("signal", "")]
    resonance = sum(1 for m in mainlines if m.get("three_resonance"))

    tl_count = sum(len(tl.get("trend_leaders", [])) for tl in trend_leaders)
    tl_qualified = sum(1 for tl in trend_leaders for s in tl.get("trend_leaders", []) if s.get("qualified"))

    parts = [
        f"\u5927\u76d8{state}(\u4ed3\u4f4d\u4e0a\u9650{position_text})",
        f"\u98ce\u683c:{style}",
        f"\u5171\u632f\u677f\u5757:{resonance}\u4e2a",
        f"\u8d8b\u52bf\u4e2d\u519b\u5019\u9009:{tl_qualified}\u53ea/\u5171{len(trend_leaders)}\u677f\u5757",
    ]
    if buy_sigs:
        parts.append(f"\u4e70\u70b9:{','.join(s['name'] for s in buy_sigs)}")
    if exit_sigs:
        parts.append(f"\u5356\u70b9:{','.join(s['name'] for s in exit_sigs)}")
    return " | ".join(parts)


def print_briefing(briefing):
    ms = briefing["market_state"]
    mst = briefing["market_style"]
    sectors = briefing["mainline_sectors"]
    alerts = briefing["buy_point_alerts"]
    action = briefing["action_summary"]

    print()
    print("=" * 72)
    print(f"  {briefing['title']}")
    print(f"  \u751f\u6210\u65f6\u95f4: {briefing['generated_at']}")
    print("=" * 72)

    print(f"\n[\u5927\u76d8\u73af\u5883 + \u4ed3\u4f4d\u7ba1\u7406]")
    print(f"  \u6307\u6570: {ms['index_name']} ({ms['index_code']})")
    lp = ms['latest_price']
    ma20v = ms['ma20']
    ty = ms['turnover_yi']
    print(f"  \u6700\u65b0\u4ef7: {lp if lp is not None else '--'}  |  MA20: {ma20v if ma20v is not None else '--'}")
    print(f"  MA20\u659c\u7387: {ms['ma20_slope_pct']:+.2f}%  |  \u72b6\u6001: {ms['state']}")
    print(f"  \u5efa\u8bae\u4ed3\u4f4d\u4e0a\u9650: {ms['position_limit_text']}")
    print(f"  \u6210\u4ea4\u989d: {ty if ty is not None else '--'}\u4ebf")
    print(f"  \u5224\u65ad\u4f9d\u636e: {ms['reason']}")

    print(f"\n[\u5e02\u573a\u98ce\u683c]")
    print(f"  \u98ce\u683c: {mst['style']}")
    print(f"  \u4e0a\u6da8{mst['rise_count']}\u5bb6 / \u4e0b\u8dcc{mst['fall_count']}\u5bb6 (\u5360\u6bd4{mst['rise_ratio']*100:.0f}%)")
    print(f"  \u6da8\u505c{mst['limit_up_count']}\u5bb6 / \u8dcc\u505c{mst['limit_down_count']}\u5bb6")
    print(f"  \u5e02\u573a\u6e29\u5ea6: {mst['market_temperature']}/100")

    LBL_SECTOR = "\u677f\u5757"
    LBL_RESON = "\u5171\u632f"
    LBL_LU = "\u6da8\u505c"
    LBL_STAT = "\u72b6\u6001"
    print(f"\n[\u5168\u90e8\u70ed\u95e8\u677f\u5757 - RPS\u6392\u5e8f]")
    all_secs = briefing.get("all_sectors", [])
    if all_secs:
        h = f"  {LBL_SECTOR:<20} {'RPS10':<8} {'RPS20':<8} {'RPS60':<8} {LBL_RESON:<6} {LBL_LU:<6}"
        print(h)
        print(f"  {'-'*64}")
        for s in all_secs:
            r10 = f"{s['rps_10']:.0f}" if s.get('rps_10') else '--'
            r20 = f"{s['rps_20']:.0f}" if s.get('rps_20') else '--'
            r60 = f"{s['rps_60']:.0f}" if s.get('rps_60') else '--'
            res = "Y" if s.get('three_resonance') else "N"
            lu = str(s.get('limit_up_num', 0))
            print(f"  {s['name']:<20} {r10:<8} {r20:<8} {r60:<8} {res:<6} {lu:<6}")
    else:
        print("  (\u65e0\u6570\u636e)")

    print(f"\n[\u4e3b\u7ebf\u677f\u5757 \u2014 RPS\u4e09\u7ebf\u5224\u5b9a]")
    LBL_SECTOR = "\u677f\u5757"
    LBL_R10 = "RPS10"
    LBL_R20 = "RPS20"
    LBL_R60 = "RPS60"
    LBL_FLAG = "\u4e09\u7ebf\u5171\u632f"
    LBL_LU = "\u6da8\u505c"
    if sectors["list"]:
        print(f"  {LBL_SECTOR:<20} {LBL_R10:<8} {LBL_R20:<8} {LBL_R60:<8} {LBL_FLAG:<10} {LBL_LU:<6}")
        print(f"  {'-'*64}")
        for s in sectors["list"]:
            r10 = f"{s['rps_10']:.0f}" if s.get('rps_10') else '--'
            r20 = f"{s['rps_20']:.0f}" if s.get('rps_20') else '--'
            r60 = f"{s['rps_60']:.0f}" if s.get('rps_60') else '--'
            res = "Y" if s.get('three_resonance') else "."
            lu = str(s.get('limit_up_num', 0))
            print(f"  {s['name']:<20} {r10:<8} {r20:<8} {r60:<8} {res:<10} {lu:<6}")
            if s.get('three_resonance'):
                nh = s.get('new_high_100d', 0)
                print(f"    \u2192 \u8be5\u677f\u5757\u5185\uff0c\u4eca\u65e5\u6709{nh}\u53ea\u4e2a\u80a1\u521b\u767e\u65e5\u65b0\u9ad8")
    else:
        print("  (\u6682\u65e0\u677f\u5757\u540c\u65f6\u6ee1\u8db3\u4e09\u7ebfRPS>=90)")

    print(f"\n[\u60c5\u7eea\u4fe1\u53f7 - \u77ed\u7ebf\u98ce\u5411\u6807]")
    # 情绪龙头作为市场风向标
    has_sentiment = False
    for sector_data in briefing.get("sentiment_dragons", []):
        dragons = sector_data.get("dragons", [])
        if not dragons:
            continue
        has_sentiment = True
        print(f"  {sector_data['sector_name']}:")
        for d in dragons[:3]:
            lu = "\u6da8\u505c" if d.get("is_limit_up_today") else ""
            cn = f"{d['continue_num']}\u8fde\u677f" if d.get("continue_num", 0) > 1 else ""
            rt = (d.get("reason_type") or "")[:20]
            print(f"    {d['name']:<10} [\u8bc4\u5206{d['dragon_score']} {d['dragon_rank']}] {lu} {cn} {rt}")
    if not has_sentiment:
        print("  (\u65e0\u60c5\u7eea\u9f99\u5934\u6570\u636e)")

    print(f"\n[\u8d8b\u52bf\u4e2d\u519b - \u673a\u6784\u5bb9\u91cf\u7968\u7b5b\u9009]")
    tl_found = False
    for tl_sector in briefing.get("trend_leaders", []):
        leaders = tl_sector.get("trend_leaders", [])
        qualified = [s for s in leaders if s.get("qualified")]
        if not leaders:
            print(f"  {tl_sector['sector_name']}: \u65e0\u6570\u636e")
            continue
        tl_found = True
        qual = tl_sector.get("qualified_count", 0)
        total = tl_sector.get("total_candidates", 0)
        note = tl_sector.get("note", "")
        print(f"  {tl_sector['sector_name']} (\u5408\u683c{qual}/{total}) {note}")
        for s in leaders:
            tag = "\u2713" if s.get("qualified") else "\u2717"
            cap = f"{s['market_cap_yi']:.0f}\u4ebf" if s.get("market_cap_yi") else "--"
            amt = f"{s['amount_5d_yi']:.1f}\u4ebf" if s.get("amount_5d_yi") else "--"
            ma_dist = f"{s['ma_distance_pct']:+.1f}%" if s.get("ma_distance_pct") is not None else "--"
            form = s.get("ma_form", "")
            pat = ""
            if s.get("has_pullback_pattern"):
                pat = " \u2193\u56de\u8e29\u7ebf"
            print(f"    {tag} {s['name']:<8} \u8bc4\u5206{s['total_score']:.0f} | \u6d41\u901a{cap} | \u6210\u4ea4{amt} | MA20\u8ddd{ma_dist} | \u5f62\u6001:{form}{pat}")
            if s.get("fails"):
                print(f"        \u672a\u8fbe\u6807: {'; '.join(s['fails'][:2])}")
    if not tl_found:
        print("  (\u65e0\u8d8b\u52bf\u4e2d\u519b\u6570\u636e)")

    print(f"\n[\u4e70\u5356\u70b9\u76d1\u63a7]")
    ba = alerts["buy_signals"]
    ea = alerts["exit_signals"]
    sw = alerts["strong_watch"]

    if ba:
        print(f"  BUY ({len(ba)}\u53ea):")
        for s in ba:
            print(f"    {s['name']} @ {s['price']} | \u6b62\u635f{s.get('stop_loss','')} | {s.get('msg','')[:50]}")
    else:
        print(f"  (\u5f53\u524d\u65e0\u4e70\u70b9\u4fe1\u53f7)")

    if ea:
        print(f"  SELL ({len(ea)}\u53ea):")
        for s in ea:
            print(f"    {s['name']} | {s.get('reason','')} | \u64cd\u4f5c:{s.get('action','')}")

    if sw:
        print(f"  WATCH ({len(sw)}\u53ea):")
        for s in sw[:5]:
            print(f"    {s['name']}: {s.get('msg','')[:50]}")

    print(f"\n[\u51b3\u7b56\u6458\u8981]")
    print(f"  {action}")

    print(f"\n[\u6a21\u578b\u53c2\u6570]")
    c = briefing["config"]
    print(f"  RPS>{c['rps_threshold']} | \u9884\u8b66RPS10<{c['rps_warn']} | \u7f29\u91cf<{c['launch_volume_shrink']}/{c['relay_volume_shrink']} | \u4e2d\u7ee7\u6da8\u5e45>={c['relay_min_gain']} | \u6700\u591a{c['max_positions']}\u53ea")
    print(f"  \u8d8b\u52bf\u4e2d\u519b: \u6d41\u901a\u5e02\u503c{c['trend_leader_min_cap']} | \u6210\u4ea4\u989d{c['trend_leader_min_amt']} | \u62d2\u7edd\u8fde\u677f | \u4ef7\u5728MA20\u4e0a+MA20\u5411\u4e0a")

    print(f"\n{'=' * 72}")
    print(f"  \u7528\u6cd5\u6307\u5357:")
    print(f"    \u60c5\u7eea\u4fe1\u53f7 = \u77ed\u7ebf\u6700\u70ed\u65b9\u5411\u7684\u98ce\u5411\u6807\uff0c\u4e0d\u662f\u4e70\u5165\u4fe1\u53f7")
    print(f"    \u8d8b\u52bf\u4e2d\u519b = \u6ce2\u6bb5\u4ea4\u6613\u6838\u5fc3\u7684\u673a\u6784\u5bb9\u91cf\u7968\uff0c\u7b49\u5f85\u4e70\u70b9")
    print(f"    \u6838\u5fc3\u539f\u5219: \u7b49\u5f85\u662f\u4ea4\u6613\u7684\u4e00\u90e8\u5206\u3002\u5206\u6e05\u5f3a\u52bf\u89c2\u5bdf\u533a\u4e0e\u7b26\u5408\u4e70\u70b9\u533a\u3002")
    print(f"{'=' * 72}")
    print()
