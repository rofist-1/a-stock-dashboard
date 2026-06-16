# -*- coding: utf-8 -*-
"""
涨停产业链异动分析模块
======================
基于 akshare 获取当日涨停池，匹配产业链标签库，
识别资金青睐的产业链/板块，输出 JSON / 控制台 / Markdown。

数据源：
  - ak.stock_zt_pool_em() 当日涨停池
  - industry_chains.json  预设产业链标签库（5条赛道 × 上/中/下游）

输出：
  - 涨停产业链异动_YYYYMMDD.json  →  供看板渲染
  - 控制台可读摘要
  - Markdown 格式文本

依赖：
  pip install akshare pandas

全局声明：
  本工具仅用于个人学习复盘，不构成任何投资建议。
  遵守 akshare 开源协议，禁止商用/违规高频爬虫。
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# 常量 / 路径
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHAINS_PATH = os.path.join(BASE_DIR, "industry_chains.json")
OUT_DIR = BASE_DIR  # JSON 输出到同一目录

# ST / 异常标的过滤关键词
ST_KEYWORDS = ("ST", "*ST", "SST", "S*ST")

# ---------------------------------------------------------------------------
# 免责声明
# ---------------------------------------------------------------------------
DISCLAIMER = """
免责声明：
  本工具仅供个人学习复盘使用，不构成任何投资建议。
  数据来源于 akshare（东方财富公开行情），版权归原作者所有。
  使用者应独立判断，自负盈亏。
"""


# ---------------------------------------------------------------------------
# 1. 加载产业链标签库
# ---------------------------------------------------------------------------
def load_chains(path: str = CHAINS_PATH) -> Dict[str, Dict[str, List[str]]]:
    """
    返回 { 链名: { 环节: [代码列表] } }
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"产业链配置文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 构建反向索引方便匹配
    return data


def build_code_to_chain(data: Dict) -> Dict[str, Tuple[str, str]]:
    """
    倒排索引：股票代码 → (链名, 环节)
    """
    mapping: Dict[str, Tuple[str, str]] = {}
    for chain_name, segments in data.items():
        for segment, codes in segments.items():
            for code in codes:
                mapping[code] = (chain_name, segment)
    return mapping


# ---------------------------------------------------------------------------
# 2. 获取涨停池
# ---------------------------------------------------------------------------
def fetch_zt_pool() -> Optional[pd.DataFrame]:
    """
    调用 akshare 的涨停池接口。
    返回 DataFrame 或 None（失败时）。
    """
    try:
        import akshare as ak
        df = ak.stock_zt_pool_em()
        if df is None or df.empty:
            print("[WARN] 涨停池数据为空（可能是非交易日）")
            return None
        return df
    except Exception as e:
        print(f"[ERROR] 获取涨停池失败: {e}")
        return None


# ---------------------------------------------------------------------------
# 3. 数据清洗
# ---------------------------------------------------------------------------
def is_st_stock(name: str) -> bool:
    """判断是否为 ST / *ST 股票"""
    if not name:
        return False
    return any(kw in name for kw in ST_KEYWORDS)


def filter_zt_pool(df: pd.DataFrame) -> pd.DataFrame:
    """
    过滤 ST 股、异常一字板（炸板次数为 0 且封板时间极早可保留）
    返回清洗后的 DataFrame
    """
    # 统一列名（akshare 版本可能不同）
    col_map = {}
    for col in df.columns:
        low = col.lower()
        if "代码" in col or col == "代码":
            col_map[col] = "code"
        elif "名称" in col or col == "名称":
            col_map[col] = "name"
        elif "涨跌幅" in col or "涨幅" in col:
            col_map[col] = "change_pct"
        elif "涨停统计" in col or "连板" in col:
            col_map[col] = "limit_stats"
        elif "封板资金" in col or col == "封板资金":
            col_map[col] = "funds"
        elif "炸板" in col:
            col_map[col] = "break_count"
        elif "行业" in col or col == "行业":
            col_map[col] = "industry"
        elif "涨停时间" in col:
            col_map[col] = "limit_time"
        elif "连板数" in col or "连板" in col:
            col_map[col] = "consecutive"
    df_clean = df.rename(columns=col_map)

    # 过滤 ST
    if "name" in df_clean.columns:
        before = len(df_clean)
        df_clean = df_clean[~df_clean["name"].apply(is_st_stock)]
        removed = before - len(df_clean)
        if removed:
            print(f"  [过滤] 剔除 {removed} 只 ST/*ST 股票")

    # 填充缺失列
    for col in ["change_pct", "funds", "break_count", "consecutive"]:
        if col not in df_clean.columns:
            df_clean[col] = 0

    return df_clean


# ---------------------------------------------------------------------------
# 4. 产业链匹配
# ---------------------------------------------------------------------------
def match_chains(
    df: pd.DataFrame, code_to_chain: Dict[str, Tuple[str, str]]
) -> List[Dict]:
    """
    逐只匹配产业链标签，返回标注后的记录列表。
    """
    records = []
    for _, row in df.iterrows():
        code = str(row.get("code", "")).strip()
        name = str(row.get("name", "")).strip()
        # 标准化代码格式（akshare 可能返回 6 位纯数字）
        if "." not in code and code.isdigit():
            if code.startswith("6") or code.startswith("9"):
                code_full = f"{code}.SH"
            elif code.startswith("0") or code.startswith("3"):
                code_full = f"{code}.SZ"
            elif code.startswith("4") or code.startswith("8"):
                code_full = f"{code}.BJ"
            else:
                code_full = code
        else:
            code_full = code.upper()

        chain_name = None
        segment = None
        if code_full in code_to_chain:
            chain_name, segment = code_to_chain[code_full]

        rec = {
            "code": code,
            "code_full": code_full,
            "name": name,
            "change_pct": float(row.get("change_pct", 0)),
            "funds": float(row.get("funds", 0)),
            "limit_time": str(row.get("limit_time", "")),
            "consecutive": int(row.get("consecutive", 0)),
            "industry": str(row.get("industry", "")),
            "chain": chain_name or "未知异动题材",
            "segment": segment or "—",
        }
        records.append(rec)
    return records


# ---------------------------------------------------------------------------
# 5. 统计汇总
# ---------------------------------------------------------------------------
def summarize(records: List[Dict], all_chains: Dict) -> Dict:
    """
    统计产业链异动，输出结构化结果
    """
    # 按链分组
    chain_groups: Dict[str, List[Dict]] = {}
    for r in records:
        chain_groups.setdefault(r["chain"], []).append(r)

    chain_stats = []
    for chain_name, stocks in chain_groups.items():
        total = len(stocks)
        first_board = sum(1 for s in stocks if s["consecutive"] == 0 or s.get("limit_time", "") == "")
        consecutive_count = sum(1 for s in stocks if s["consecutive"] > 1)
        # 代表性个股（涨停时间最早或封板资金最大）
        sorted_stocks = sorted(
            stocks,
            key=lambda s: (s["funds"], -stocks.index(s)),
            reverse=True,
        )
        top_reps = sorted_stocks[:3]

        # 上下游拆解（已知链才拆）
        segment_breakdown = {}
        if chain_name in all_chains:
            for seg_name in all_chains[chain_name]:
                seg_stocks = [s for s in stocks if s["segment"] == seg_name]
                if seg_stocks:
                    segment_breakdown[seg_name] = {
                        "count": len(seg_stocks),
                        "stocks": [s["name"] for s in seg_stocks],
                    }

        chain_stats.append({
            "chain": chain_name,
            "total": total,
            "first_board": first_board,
            "consecutive_count": consecutive_count,
            "representative": [
                {"name": s["name"], "code": s["code"], "funds": s["funds"]}
                for s in top_reps
            ],
            "segment_breakdown": segment_breakdown,
            "stocks": [
                {
                    "name": s["name"],
                    "code": s["code"],
                    "change_pct": s["change_pct"],
                    "consecutive": s["consecutive"],
                    "segment": s["segment"],
                }
                for s in stocks
            ],
        })

    # 按涨停总数降序排序
    chain_stats.sort(key=lambda c: c["total"], reverse=True)

    # 未知异动个股列表
    unknown = [r for r in records if r["chain"] == "未知异动题材"]

    top3 = chain_stats[:3]

    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_limit_up": len(records),
        "total_chains_matched": len([c for c in chain_stats if c["chain"] != "未知异动题材"]),
        "top3": top3,
        "all_chains": chain_stats,
        "unknown_count": len(unknown),
        "unknown_stocks": [
            {
                "name": s["name"],
                "code": s["code"],
                "consecutive": s["consecutive"],
                "change_pct": s["change_pct"],
            }
            for s in unknown
        ],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "disclaimer": "本工具仅用于个人学习复盘，不构成任何投资建议",
    }
    return result


# ---------------------------------------------------------------------------
# 6. 输出格式
# ---------------------------------------------------------------------------
def format_console(result: Dict) -> str:
    """控制台可读文本"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"  涨停产业链异动分析  [{result['date']}]")
    lines.append("=" * 60)
    lines.append(f"  涨停总数: {result['total_limit_up']}")
    lines.append(f"  匹配产业链数: {result['total_chains_matched']}")
    lines.append(f"  未知异动: {result['unknown_count']} 只")
    lines.append("")

    for i, chain in enumerate(result["top3"], 1):
        lines.append(f"  ── TOP{i}: {chain['chain']}（{chain['total']}只涨停）──")
        lines.append(f"      首板: {chain['first_board']}  连板: {chain['consecutive_count']}")
        if chain["representative"]:
            reps = ", ".join(f"{s['name']}({s['code']})" for s in chain["representative"])
            lines.append(f"      代表: {reps}")
        for seg_name, seg_data in chain["segment_breakdown"].items():
            stocks_str = ", ".join(seg_data["stocks"][:5])
            suf = "..." if len(seg_data["stocks"]) > 5 else ""
            lines.append(f"      {seg_name}: {seg_data['count']}只 → {stocks_str}{suf}")
        lines.append("")

    if result["unknown_stocks"]:
        lines.append("  ── 未知异动题材 ──")
        unknown_str = ", ".join(
            f"{s['name']}({s['code']})" for s in result["unknown_stocks"][:10]
        )
        suf = "..." if len(result["unknown_stocks"]) > 10 else ""
        lines.append(f"    {unknown_str}{suf}")
        lines.append("")

    lines.append("-" * 60)
    lines.append(DISCLAIMER.strip())
    return "\n".join(lines)


def format_markdown(result: Dict) -> str:
    """Markdown 格式文本"""
    lines = []
    lines.append(f"## 涨停产业链异动分析  {result['date']}")
    lines.append("")
    lines.append(f"- **涨停总数**: {result['total_limit_up']}")
    lines.append(f"- **匹配产业链数**: {result['total_chains_matched']}")
    lines.append(f"- **未知异动**: {result['unknown_count']} 只")
    lines.append("")

    for i, chain in enumerate(result["top3"], 1):
        lines.append(f"### TOP{i}: {chain['chain']}（{chain['total']}只涨停）")
        lines.append(f"- 首板: {chain['first_board']} / 连板: {chain['consecutive_count']}")
        if chain["representative"]:
            reps = "、".join(f"`{s['name']}({s['code']})`" for s in chain["representative"])
            lines.append(f"- 代表个股: {reps}")
        for seg_name, seg_data in chain["segment_breakdown"].items():
            stocks_str = "、".join(seg_data["stocks"])
            lines.append(f"- **{seg_name}**（{seg_data['count']}只）: {stocks_str}")
        lines.append("")

    if result["unknown_stocks"]:
        lines.append("### 未知异动题材")
        unknown_str = "、".join(
            f"`{s['name']}({s['code']})`" for s in result["unknown_stocks"]
        )
        lines.append(f"{unknown_str}")
        lines.append("")

    lines.append("---")
    lines.append("> 本工具仅用于个人学习复盘，不构成任何投资建议。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 7. 保存 JSON
# ---------------------------------------------------------------------------
def save_json(result: Dict, out_dir: str = OUT_DIR):
    """保存结构化 JSON 供看板使用"""
    date_str = datetime.now().strftime("%Y%m%d")
    path = os.path.join(out_dir, f"涨停产业链异动_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  [SAVE] {path}")
    return path


# ---------------------------------------------------------------------------
# 8. 主流程
# ---------------------------------------------------------------------------
def main():
    print(DISCLAIMER)
    print()

    # 加载产业链配置
    try:
        all_chains = load_chains()
        code_to_chain = build_code_to_chain(all_chains)
        print(f"[OK] 加载产业链: {list(all_chains.keys())}")
    except FileNotFoundError as e:
        print(f"[FATAL] {e}")
        sys.exit(1)

    # 获取涨停池
    df_zt = fetch_zt_pool()
    if df_zt is None or df_zt.empty:
        print("[SKIP] 涨停池为空，退出")
        # 生成一个空的占位 JSON 避免看板报错
        empty_result = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_limit_up": 0,
            "total_chains_matched": 0,
            "top3": [],
            "all_chains": [],
            "unknown_count": 0,
            "unknown_stocks": [],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "disclaimer": "本工具仅用于个人学习复盘，不构成任何投资建议",
        }
        save_json(empty_result)
        return

    # 清洗
    df_clean = filter_zt_pool(df_zt)
    if df_clean.empty:
        print("[SKIP] 过滤后涨停池为空")
        return

    # 匹配
    records = match_chains(df_clean, code_to_chain)
    print(f"[OK] 匹配完成，{len(records)} 只涨停股")

    # 统计
    result = summarize(records, all_chains)

    # 输出
    print("\n" + format_console(result))
    print("\n" + "=" * 60)

    md = format_markdown(result)
    print("\n[Markdown 格式]\n")
    print(md)

    # 保存
    save_json(result)


if __name__ == "__main__":
    main()
