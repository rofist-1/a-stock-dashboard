# -*- coding: utf-8 -*-
"""
CLI 入口
========
用法:
  python -m wave_trading_model           # 每日简报 (默认)
  python -m wave_trading_model market     # 只看大盘
  python -m wave_trading_model sectors    # 只看板块
  python -m wave_trading_model dragons    # 只看龙头
  python -m wave_trading_model clearcache # 清理缓存
"""

import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# avoid relative import failures
import sys, os
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)
import config
from briefing import generate_briefing, print_briefing
from market_state import analyze_market
from market_style import analyze_style
from sector_analysis import get_mainline_sectors
from stock_screener import screen_all_mainline_dragons
from data_fetcher import clear_cache


def cmd_briefing():
    b = generate_briefing()
    print_briefing(b)


def cmd_market():
    m = analyze_market()
    s = analyze_style()
    print(f"\n大盘状态: {m['state']}")
    print(f"仓位上限: {m['position_limit_text']}")
    print(f"MA20斜率: {m['ma20_slope_pct']:+.2f}%")
    print(f"市场风格: {s['style']}")
    print(f"涨跌比: {s['rise_count']}/{s['fall_count']} (上涨占比{s['rise_ratio']*100:.0f}%)")
    print(f"温度: {s['market_temperature']}/100")
    print(f"依据: {m['reason']}")


def cmd_sectors():
    ml = get_mainline_sectors(limit=config.SECTOR_TOP_N)
    print(f"\n主线板块 (RPS>{config.RPS_THRESHOLD_LEADER}):")
    for s in ml:
        r10 = f"{s['rps_10']:.0f}" if s.get('rps_10') else '--'
        r20 = f"{s['rps_20']:.0f}" if s.get('rps_20') else '--'
        r60 = f"{s['rps_60']:.0f}" if s.get('rps_60') else '--'
        res = "Y" if s.get('three_resonance') else "N"
        print(f"  {s['name']:<16} RPS({r10}/{r20}/{r60}) 共振={res} 涨停{s['limit_up_num']}")


def cmd_dragons():
    ml = get_mainline_sectors(limit=3)
    dragons = screen_all_mainline_dragons(ml, limit_per_sector=3)
    for ds in dragons:
        print(f"\n{ds['sector_name']}:")
        for d in ds.get("dragons", []):
            lu = " [涨停]" if d.get("is_limit_up_today") else ""
            cn = f" {d['continue_num']}连板" if d.get("continue_num", 0) > 1 else ""
            print(f"  {d['name']} | 评分{d['dragon_score']} | {d['dragon_rank']}{lu}{cn}")
        if not ds.get("dragons"):
            print(f"  (无数据)")


def cmd_cache():
    cleared = clear_cache(0)
    print(f"已清理 {cleared} 个缓存文件")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="波段交易模型决策辅助系统")
    parser.add_argument("cmd", nargs="?", default="briefing",
                        choices=["briefing", "market", "sectors", "dragons", "clearcache"])
    args = parser.parse_args()

    cmds = {
        "briefing": cmd_briefing,
        "market": cmd_market,
        "sectors": cmd_sectors,
        "dragons": cmd_dragons,
        "clearcache": cmd_cache,
    }
    cmds[args.cmd]()


if __name__ == "__main__":
    main()
