# -*- coding: utf-8 -*-
"""
涨停产业链异动分析模块 (悟道API版)
==============================
基于悟道 A 股数据 API 获取当日涨停池，按行业/涨停原因归类输出 JSON。

数据源：
  - wudao_client.get_limit_up_filter()   当日涨停池（含涨停原因、连板数、行业等）
  - wudao_client.get_hot_sectors()       最强风口（板块聚合）
  - wudao_client.get_limit_stats()       涨跌停统计

输出：
  - 涨停产业链异动_YYYYMMDD.json  → 供看板渲染

兼容看板预期字段：
  date, total_limit_up, total_chains_matched, top3, all_chains,
  unknown_count, unknown_stocks
"""

import json
import os
import sys
from datetime import datetime
from collections import defaultdict

# 改用悟道 API 客户端
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wudao_client import get_limit_up_filter, get_hot_sectors, get_limit_stats

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = BASE_DIR

# 预定义产业链标签（可选，作为 industry 的补充分组）
CHAIN_OVERRIDE = {
    "芯片":    {"电子器件", "电子信息", "半导体", "元器件"},
    "机器人":  {"机械行业", "专用机械", "电器仪表", "纺织机械", "通用机械"},
    "新能源":  {"电气设备", "电力设备", "新能源车", "汽车配件"},
    "人工智能":{"软件服务", "互联网", "IT设备", "通信设备"},
    "军工":    {"航空", "船舶", "国防军工"},
}


def get_today_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def classify_chain_by_industry(industry: str, reason_type: str = "") -> str:
    """根据行业和涨停原因判断所属产业链"""
    # 先按 reason_type 关键词匹配
    rt = reason_type or ""
    for chain, keywords in {
        "芯片":     ["芯片", "半导体", "光刻", "封测", "晶圆", "IC", "集成电路", "存储", "先进封装", "PCB", "铜箔", "覆铜板"],
        "机器人":   ["机器人", "减速器", "伺服", "数控", "机器视觉", "工业母机", "人形"],
        "新能源":   ["锂电", "光伏", "新能源", "钙钛矿", "风电", "储能", "充电"],
        "人工智能": ["AI", "算力", "大模型", "CPO", "光模块", "数据要素", "人工智能", "软件"],
        "低空经济": ["低空", "飞行汽车", "eVTOL", "无人机"],
        "军工":     ["军工", "航天", "大飞机", "船舶"],
    }.items():
        for kw in keywords:
            if kw in rt:
                return chain

    # 再按行业匹配
    ind = industry or ""
    for chain, sectors in CHAIN_OVERRIDE.items():
        if ind in sectors:
            return chain
    return ind  # fallback to industry name


def main(date_str: str = None):
    if date_str is None:
        date_str = get_today_str()

    display_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

    # 1. 获取涨停池
    print(f"[INFO] Fetching limit-up pool via 悟道API for {display_date}...")
    try:
        stocks = get_limit_up_filter(date=date_str, limit=200)
    except Exception as e:
        print(f"[ERROR] Failed to fetch limit-up pool: {e}")
        _write_empty(date_str, display_date)
        return

    if not stocks:
        print("[INFO] No limit-up stocks today.")
        _write_empty(date_str, display_date)
        return

    total_limit_up = len(stocks)
    print(f"[INFO] Total limit-up via 悟道: {total_limit_up}")

    # 2. 获取热点板块和统计（仅用于补充信息）
    try:
        hot_sectors = get_hot_sectors(date=date_str)
        stats = get_limit_stats(date=date_str)
    except Exception:
        hot_sectors = []
        stats = {}

    # 3. 解析每只涨停股
    stocks_info = []
    for s in stocks:
        code = str(s.get("code", "")).strip()
        name = str(s.get("name", "")).strip()
        industry = str(s.get("industry", "")).strip() or "其他"
        reason_type = str(s.get("reason_type", "")).strip()
        change_rate = float(s.get("change_rate", 0) or 0)
        continue_num = int(s.get("continue_num", 0) or 0)
        order_amount = float(s.get("order_amount", 0) or 0)
        order_volume = float(s.get("order_volume", 0) or 0)
        first_limit_up_time = str(s.get("first_limit_up_time", ""))
        last_limit_up_time = str(s.get("last_limit_up_time", ""))
        open_num = s.get("open_num")  # may be None
        limit_up_type = str(s.get("limit_up_type", "")).strip()
        trading_amount = float(s.get("trading_amount", 0) or 0)
        currency_value = float(s.get("currency_value", 0) or 0)
        turnover_rate = float(s.get("turnover_rate", 0) or 0)
        change_tag = str(s.get("change_tag", "")).strip()

        # 补齐后缀
        code_clean = code.replace(".SH", "").replace(".SZ", "").replace(".BJ", "").strip()

        # 判断所属产业链
        chain_name = classify_chain_by_industry(industry, reason_type)

        stocks_info.append({
            "code": code_clean,
            "name": name,
            "industry": industry,
            "reason_type": reason_type,
            "change_rate": change_rate,
            "continue_num": continue_num,
            "order_amount": order_amount,
            "order_volume": order_volume,
            "first_limit_up_time": first_limit_up_time,
            "last_limit_up_time": last_limit_up_time,
            "open_num": open_num,
            "limit_up_type": limit_up_type,
            "trading_amount": trading_amount,
            "currency_value": currency_value,
            "turnover_rate": turnover_rate,
            "change_tag": change_tag,
            "chain_name": chain_name,
        })

    # 4. 按产业链分组
    chain_stocks = defaultdict(list)
    for s in stocks_info:
        cn = s["chain_name"] or "其他"
        chain_stocks[cn].append(s)

    # 5. 构建 all_chains
    all_chains = []
    for cn, cstocks in chain_stocks.items():
        total = len(cstocks)
        first_board = len([s for s in cstocks if s["continue_num"] <= 1])
        consecutive_count = total - first_board
        reps = sorted(cstocks, key=lambda x: -x["continue_num"])[:3]

        # 提取 high_board 信息
        max_continue = max((s["continue_num"] for s in cstocks), default=0)
        high_board_desc = f"{max_continue}连板" if max_continue >= 2 else "首板"

        # 统计 reason_type 分布
        reason_summary = defaultdict(int)
        for s in cstocks:
            if s["reason_type"]:
                for part in s["reason_type"].split("+"):
                    part = part.strip()
                    if part:
                        reason_summary[part] += 1
        top_reasons = sorted(reason_summary.items(), key=lambda x: -x[1])[:5]

        # 查找该链在 hot_sectors 中的信息
        sector_hot_info = {}
        for hs in hot_sectors:
            if hs.get("name") == cn or cn in hs.get("name", ""):
                sector_hot_info = {
                    "sector_change": hs.get("changePercent"),
                    "sector_limit_up": hs.get("limitUpNum"),
                    "sector_high_board": hs.get("highBoard"),
                    "sector_days": hs.get("days"),
                }
                break

        all_chains.append({
            "chain": cn,
            "total": total,
            "first_board": first_board,
            "consecutive_count": consecutive_count,
            "high_board": high_board_desc,
            "max_continue": max_continue,
            "top_reasons": [{"keyword": k, "count": v} for k, v in top_reasons],
            "representative": [
                {
                    "name": s["name"],
                    "code": s["code"],
                    "continue_num": s["continue_num"],
                    "reason_type": s["reason_type"],
                    "order_amount": s["order_amount"],
                }
                for s in reps
            ],
            **sector_hot_info,
        })

    # 按总涨停数降序
    all_chains.sort(key=lambda x: -x["total"])
    top3 = all_chains[:3]

    # 6. 构建统计信息
    total_chains = len(all_chains)

    # 连板分布
    continue_dist = defaultdict(int)
    for s in stocks_info:
        continue_dist[s["continue_num"]] += 1
    board_distribution = [
        {"level": k, "count": v}
        for k, v in sorted(continue_dist.items(), key=lambda x: -x[0])
    ]

    output = {
        "date": display_date,
        "total_limit_up": total_limit_up,
        "total_chains_matched": total_chains,
        "top3": top3,
        "all_chains": all_chains,
        "board_distribution": board_distribution,
        "hot_sectors_top": [
            {"name": hs.get("name"), "limitUpNum": hs.get("limitUpNum"),
             "continuousPlateNum": hs.get("continuousPlateNum"),
             "highBoard": hs.get("highBoard")}
            for hs in hot_sectors[:10]
        ],
        "stats": {
            "sealed_limit_up": stats.get("sealedLimitUp"),
            "touched_limit_up": stats.get("touchedLimitUp"),
            "broken_limit_up": stats.get("brokenLimitUp"),
            "seal_rate": stats.get("limitUpSealRate"),
            "sealed_limit_down": stats.get("sealedLimitDown"),
        },
        "unknown_count": 0,
        "unknown_stocks": [],
    }

    out_path = os.path.join(OUT_DIR, f"涨停产业链异动_{date_str}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Output: {out_path}")
    print(f"[INFO] 涨停总数: {total_limit_up}")
    print(f"[INFO] 产业链数: {total_chains}")
    print(f"[INFO] TOP3: {[c['chain'] for c in top3]}")
    if stats:
        print(f"[INFO] 封板率: {stats.get('limitUpSealRate', '?')} 炸板: {stats.get('brokenLimitUp', '?')}")
    print("\n=== 产业链异动摘要 ===")
    for c in all_chains:
        reps_str = ", ".join(f"{r['name']}({r['continue_num']}板)" for r in c["representative"])
        print(f"  {c['chain']}: {c['total']}只 (首板{c['first_board']} 连板{c['consecutive_count']}) [{c['high_board']}] 代表:{reps_str}")
        if c.get("top_reasons"):
            reasons = " ".join(f"{r['keyword']}({r['count']})" for r in c["top_reasons"][:3])
            print(f"    原因: {reasons}")


def _write_empty(date_str: str, display_date: str):
    empty = {
        "date": display_date,
        "total_limit_up": 0,
        "total_chains_matched": 0,
        "top3": [],
        "all_chains": [],
        "board_distribution": [],
        "hot_sectors_top": [],
        "stats": {},
        "unknown_count": 0,
        "unknown_stocks": [],
    }
    out_path = os.path.join(OUT_DIR, f"涨停产业链异动_{date_str}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(empty, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Empty output: {out_path}")


if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(date_arg)
