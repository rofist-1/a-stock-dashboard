"""
主线板块发现与验证模块
=====================
主线发现策略：
1. 热门板块（hot_sectors）按涨停集中度排名
2. RPS 估算 = f(板块涨幅, 涨停数)
3. 验证三线共振：板块涨幅 + 涨停密度 + 强势股数量
"""

from datetime import datetime
# avoid relative import failures
import sys, os
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)
import config
from data_fetcher import get_hot_sectors


def _count_strong_pool_new_high(sector_name):
    """使用悟道API统计该行业强势股池百日新高数量"""
    try:
        from data_fetcher import _call_wudao
        data = _call_wudao("stock_screener", {"industryKeywords": [sector_name], "limit": 50, "detailLevel": "standard"})
        if not data or not isinstance(data, list):
            return 0
        cnt = 0
        for r in data:
            chg = float(r.get("closePctChg", r.get("pct_chg", 0) or 0))
            if chg > 5:
                cnt += 1
        return cnt
    except:
        return 0


# ———————————————— 板块名称别名映射 ————————————————
SECTOR_ALIAS_MAP = {
    "芯片":      ["半导体", "芯片", "集成电路", "电子"],
    "元器件":    ["元件", "元器件", "电子元件"],
    "化工":      ["化学制品", "化工", "化学原料", "化学"],
    "机器人":    ["机器人概念", "机器人", "自动化设", "通用设备"],
    "通信":      ["通信", "5G", "光通信", "通信设备"],
    "算力":      ["算力", "人工智能", "AI", "数据中心", "云计算", "计算机", "软件"],
    "低空经济":  ["低空经济", "商业航天", "航天", "航空"],
    "光伏":      ["光伏设备", "光伏", "太阳能"],
    "储能":      ["储能", "锂电池", "电池", "新能源"],
    "汽车":      ["汽车零部", "新能源汽车", "汽车", "整车"],
    "金融":      ["证券", "银行", "保险", "金融"],
    "医药":      ["化学制药", "化学制品", "生物制品", "医药", "中药", "医疗", "创新药", "医药生物"],
    "有色金属":  ["有色金属", "有色", "黄金", "金属"],
    "面板":      ["光学光电", "面板", "显示", "电子", "消费电子"],
}


def _name_resolve(user_name, existing_names):
    """将用户板块名映射到RPS系统中的板块名"""
    if user_name in existing_names:
        return user_name
    if user_name in SECTOR_ALIAS_MAP:
        for alias in SECTOR_ALIAS_MAP[user_name]:
            for en in existing_names:
                if alias in en or en in alias:
                    return en
    for en in existing_names:
        if user_name in en or en in user_name:
            return en
    return None


def analyze_sectors(limit=config.SECTOR_TOP_N, new_high_data=None):
    """
    new_high_data: [(板块名称, 百日新高总数, 今日新增, "hot"|"watch"), ...]
    返回: [dict, ...] 每个dict包含原始RPS和百日新高加成后的最终RPS
    """
    hot = get_hot_sectors()
    if not hot:
        return _fallback(limit)

    # 构建百日新高加速索引：RPS系统名 → (总数, 新增, 分类)
    nh_boost = {}
    existing_names = [s.get("name", "") for s in hot if s.get("name")]
    for nh_item in (new_high_data or []):
        nh_name = nh_item[0]
        resolved = _name_resolve(nh_name, existing_names)
        key = resolved or nh_name  # 未匹配也保留原名
        nh_boost[key] = (nh_item[1], nh_item[2], nh_item[3])

    all_sectors_data = []
    raw_scores = []  # 用百分位排名替代线性公式

    for sector in hot:
        name = sector.get("name", "")
        limit_up_num = sector.get("limitUpNum", 0) or sector.get("limitUpCount", 0) or 0
        change_pct = sector.get("changePercent", 0) or 0
        stocks_data = sector.get("stocks", [])

        stock_codes = [s.get("code", "") for s in stocks_data if s.get("code")] if stocks_data else []
        stock_names = [s.get("name", "") for s in stocks_data if s.get("name")] if stocks_data else []

        continuous_num = sector.get("continuousPlateNum", 0) or 0

        # 综合得分（不同时间窗口权重不同）
        score_10 = limit_up_num * 0.5 + change_pct * 0.3 + continuous_num * 2
        score_20 = limit_up_num * 0.4 + change_pct * 0.2 + continuous_num * 2
        score_60 = limit_up_num * 0.3 + change_pct * 0.1 + continuous_num * 3
        raw_scores.append((name, limit_up_num, change_pct, continuous_num, stock_codes, stock_names,
                           stocks_data, score_10, score_20, score_60))

    # 百分位排名 → RPS
    n = len(raw_scores)
    for i, (name, limit_up_num, change_pct, continuous_num, stock_codes, stock_names,
            stocks_data, s10, s20, s60) in enumerate(raw_scores):

        # 百分位: 比s10小的占比
        rank_10 = sum(1 for _ in raw_scores if _[7] <= s10) / max(n, 1) * 100
        rank_20 = sum(1 for _ in raw_scores if _[8] <= s20) / max(n, 1) * 100
        rank_60 = sum(1 for _ in raw_scores if _[9] <= s60) / max(n, 1) * 100

        rps10_raw = max(0, min(100, rank_10))
        rps20_raw = max(0, min(100, rank_20))
        rps60_raw = max(0, min(100, rank_60))

        # 百日新高加成：存量×0.12 + 新增×0.35，上限20分
        nhb = 0
        if name in nh_boost:
            total_nh, new_nh, cat = nh_boost[name]
            nhb = min(20, total_nh * 0.12 + new_nh * 0.35)
            nhb = round(nhb, 1)

        rps10_est = max(0, min(100, rps10_raw + nhb))
        rps20_est = max(0, min(100, rps20_raw + nhb))
        rps60_est = max(0, min(100, rps60_raw + nhb))

        three = (
            rps10_est >= config.RPS_THRESHOLD_LEADER and
            rps20_est >= config.RPS_THRESHOLD_LEADER and
            rps60_est >= config.RPS_THRESHOLD_LEADER
        )

        nh_count = sum(1 for s in stocks_data if s.get("changePercent", 0) or 0 > 5) if stocks_data else 0
        new_high_100d = _count_strong_pool_new_high(name)

        all_sectors_data.append({
            "ts_code": name,
            "name": name,
            "pct_chg": change_pct,
            "limit_up_num": limit_up_num,
            "stock_count": len(stock_codes),
            "rps_10_raw": round(rps10_raw, 1),
            "rps_20_raw": round(rps20_raw, 1),
            "rps_60_raw": round(rps60_raw, 1),
            "rps_10": round(rps10_est, 1),
            "rps_20": round(rps20_est, 1),
            "rps_60": round(rps60_est, 1),
            "rps_nh_boost": nhb,
            "three_resonance": three,
            "new_high_count": nh_count,
            "new_high_100d": new_high_100d,
            "status": "主线共振" if three else "观察",
            "rps_warning": rps10_est < config.RPS_WARN_THRESHOLD,
            "rps_exit": rps60_est < config.RPS_EXIT_THRESHOLD,
            "stocks": stock_codes,
            "stock_names": stock_names,
        })

    all_sectors_data.sort(key=lambda x: (
        x["three_resonance"],
        x["limit_up_num"],
        x.get("new_high_count", 0),
    ), reverse=True)

    return all_sectors_data


def _fallback(limit):
    return []


def get_mainline_sectors(limit=config.SECTOR_TOP_N, new_high_data=None):
    all_s = analyze_sectors(limit=limit * 2, new_high_data=new_high_data)
    ml = [s for s in all_s if s["three_resonance"]]
    if not ml:
        all_s.sort(key=lambda x: x.get("limit_up_num", 0), reverse=True)
        ml = all_s[:min(limit, len(all_s))]
    return ml[:limit]
