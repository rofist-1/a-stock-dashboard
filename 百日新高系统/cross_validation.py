# -*- coding: utf-8 -*-
"""
百日新高-涨停异动交叉校验模块
==============================
联动「涨停产业链异动分析」与「百日新高板块数据」，
做交叉对比、信号校验，区分 4 类市场情景。
输出结构化 JSON 供看板渲染。

数据源（只读，不修改任何原有文件）：
  - 涨停产业链异动_YYYYMMDD.json  (chain_analysis.py 输出)
  - 百日新高_YYYYMMDD.json         (scanner_akshare.py 输出)

判定逻辑：
  1. 强共振信号    → 涨停TOP板块与百日新高集中板块高度重合
  2. 纯短线脉冲    → 板块涨停多但无对应百日新高标的
  3. 慢趋势行情    → 百日新高多但几乎无涨停
  4. 市场分化混沌  → 涨停题材与百日新高方向完全割裂

全局声明：
  本工具仅用于个人学习复盘，不构成任何投资建议。
  遵守 akshare 开源协议，禁止商用/违规高频爬虫。
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 常量 / 路径
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = BASE_DIR

# 百日新高系统输出目录（与交叉校验在同一目录）
NEW_HIGH_DIR = BASE_DIR

# ---------------------------------------------------------------------------
# 免责声明
# ---------------------------------------------------------------------------
DISCLAIMER = """
免责声明：
  本工具仅供个人学习复盘使用，不构成任何投资建议。
  数据来源于公开行情，版权归原作者所有。
"""

# ---------------------------------------------------------------------------
# 文件查找
# ---------------------------------------------------------------------------
def find_latest_json(pattern: str, search_dir: str) -> Optional[str]:
    """
    在指定目录查找最新的匹配 JSON 文件。
    pattern: 如 "涨停产业链异动_*", "百日新高_*"
    """
    import glob
    files = glob.glob(os.path.join(search_dir, pattern))
    if not files:
        return None
    # 按修改时间排序，取最新的
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return files[0]


def find_latest_new_high() -> Optional[str]:
    """查找最新的百日新高 JSON"""
    return find_latest_json("百日新高_20*.json", NEW_HIGH_DIR)


def find_latest_chain() -> Optional[str]:
    """查找最新的涨停产业链异动 JSON"""
    return find_latest_json("涨停产业链异动_20*.json", OUT_DIR)


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------
def load_json(path: str) -> Optional[Dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] 读取 {path} 失败: {e}")
        return None


# ---------------------------------------------------------------------------
# 板块重合度计算
# ---------------------------------------------------------------------------
def extract_top_sectors_from_new_high(data: Dict, top_n: int = 5) -> List[str]:
    """
    从百日新高数据提取集中板块（sector 字段出现最多的前 N 个）
    返回板块名称列表（去重，小写）
    """
    stocks = data.get("stocks", [])
    if not stocks:
        return []

    sector_count: Dict[str, int] = {}
    for s in stocks:
        sec = s.get("sector", "").strip()
        if sec and sec != "其他":
            sector_count[sec] = sector_count.get(sec, 0) + 1

    sorted_sectors = sorted(sector_count.items(), key=lambda x: x[1], reverse=True)
    top_sectors = [s[0] for s in sorted_sectors[:top_n]]
    return top_sectors


def extract_chain_related_sectors(chain_result: Dict) -> List[str]:
    """
    从涨停产业链异动结果提取相关板块名称。
    返回去重小写列表（含链名 + 个股 industry 字段）。
    """
    sectors = set()
    for c in chain_result.get("all_chains", []):
        sectors.add(c["chain"].lower())
        for s in c.get("stocks", []):
            ind = s.get("industry", "").strip()
            if ind and ind != "其他":
                sectors.add(ind.lower())
    for s in chain_result.get("unknown_stocks", []):
        pass  # 未知异动暂不加入
    return list(sectors)


def compute_overlap(
    top_new_high_sectors: List[str],
    chain_related: List[str],
) -> Tuple[float, List[str]]:
    """
    计算重合度。
    返回 (重合比例 0-1, 重合板块列表)
    """
    nh_lower = [s.lower() for s in top_new_high_sectors]

    # 将链名与板块做模糊匹配
    overlap = []
    for chain_sec in chain_related:
        if chain_sec in nh_lower:
            overlap.append(chain_sec)
    # 去重
    overlap = list(set(overlap))

    if not top_new_high_sectors:
        return 0.0, overlap

    ratio = len(overlap) / len(top_new_high_sectors)
    return ratio, overlap


# ---------------------------------------------------------------------------
# 情景判定
# ---------------------------------------------------------------------------
def classify_scenario(
    chain_result: Dict,
    new_high_result: Dict,
    overlap_ratio: float,
    overlap_sectors: List[str],
) -> Dict:
    """
    判定 4 类市场情景并给出解读。
    """
    total_limit_up = chain_result.get("total_limit_up", 0)
    total_new_high = new_high_result.get("total", 0)
    top3 = chain_result.get("top3", [])
    top3_total = sum(c.get("total", 0) for c in top3)
    unknown_count = chain_result.get("unknown_count", 0)

    # 是否有明确的涨停主线
    has_clear_chain = len(top3) > 0 and top3[0].get("total", 0) >= 3

    # 百日新高是否集中
    stocks = new_high_result.get("stocks", [])
    sector_count = {}
    for s in stocks:
        sec = s.get("sector", "").strip()
        if sec and sec != "其他":
            sector_count[sec] = sector_count.get(sec, 0) + 1
    top_new_high_count = max(sector_count.values()) if sector_count else 0
    has_concentrated_new_high = top_new_high_count >= 5

    # 判定
    if overlap_ratio >= 0.4 and has_clear_chain and has_concentrated_new_high:
        scenario = "强共振信号"
        detail = (
            f"涨停异动TOP板块与百日新高集中板块高度重合"
            f"（重合度{overlap_ratio:.0%}），"
            f"短线进攻+中期抱团共振，主线确定性强。"
        )
    elif has_clear_chain and overlap_ratio < 0.2:
        scenario = "纯短线脉冲"
        detail = (
            f"涨停集中在{top3[0]['chain']}等板块，"
            f"但百日新高标的中几乎无对应板块个股，"
            f"偏向消息驱动短线炒作，警惕一日游风险。"
        )
    elif not has_clear_chain and has_concentrated_new_high and total_new_high > 50:
        scenario = "慢趋势行情"
        detail = (
            f"百日新高数量较多（{total_new_high}只）且集中在少数板块，"
            f"但涨停异动不明显（仅{total_limit_up}只涨停），"
            f"中期资金慢推趋势，适合趋势跟踪。"
        )
    else:
        scenario = "市场分化混沌"
        detail = (
            f"涨停炒作题材与百日新高集中方向不一致，"
            f"资金分歧大，暂无统一主线，操作难度偏高。"
        )

    # 主线共振度
    resonance_score = round(overlap_ratio * 100, 1)

    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "scenario": scenario,
        "detail": detail,
        "resonance_score": resonance_score,
        "overlap_sectors": overlap_sectors,
        "overlap_ratio": round(overlap_ratio, 2),
        "metrics": {
            "total_limit_up": total_limit_up,
            "total_new_high": total_new_high,
            "top3_chain_count": top3_total,
            "unknown_limit_up": unknown_count,
        },
        "disclaimer": "本工具仅用于个人学习复盘，不构成任何投资建议",
    }
    return result


# ---------------------------------------------------------------------------
# 保存 JSON
# ---------------------------------------------------------------------------
def save_json(result: Dict, out_dir: str = OUT_DIR):
    date_str = datetime.now().strftime("%Y%m%d")
    path = os.path.join(out_dir, f"交叉校验_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  [SAVE] {path}")
    return path


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    print(DISCLAIMER)
    print()

    # 查找数据文件
    chain_path = find_latest_chain()
    nh_path = find_latest_new_high()

    if not chain_path:
        print("[SKIP] 未找到涨停产业链异动 JSON，请先运行 chain_analysis.py")
        return
    if not nh_path:
        print("[SKIP] 未找到百日新高 JSON，请先运行扫描器")
        return

    print(f"[OK] 涨停数据: {chain_path}")
    print(f"[OK] 百日新高:  {nh_path}")

    chain_result = load_json(chain_path)
    nh_result = load_json(nh_path)
    if not chain_result or not nh_result:
        print("[FATAL] 数据加载失败")
        return

    # 提取板块
    top_nh = extract_top_sectors_from_new_high(nh_result, top_n=5)
    chain_sectors = extract_chain_related_sectors(chain_result)

    print(f"  百日新高集中板块: {top_nh}")
    print(f"  涨停相关板块:     {chain_sectors}")

    # 计算重合度
    overlap_ratio, overlap_sectors = compute_overlap(top_nh, chain_sectors)
    print(f"  重合度: {overlap_ratio:.0%}  ({overlap_sectors})")

    # 判定
    result = classify_scenario(chain_result, nh_result, overlap_ratio, overlap_sectors)

    print(f"\n  >>> 判定: {result['scenario']}")
    print(f"  >>> {result['detail']}")
    print(f"  >>> 主线共振度: {result['resonance_score']}")

    # 保存
    save_json(result)


if __name__ == "__main__":
    main()
