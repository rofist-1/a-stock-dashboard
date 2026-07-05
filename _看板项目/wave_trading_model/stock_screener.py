# -*- coding: utf-8 -*-
"""
龙头个股筛选模块
===============
两套独立体系:
  1. 情绪龙头 - 原有"龙头三问"逻辑，识别短线情绪票，用作市场风向标
  2. 趋势中军 - 新增量化筛选，只做机构容量票，波段交易核心标的
"""

from datetime import datetime, timedelta

# 避免相对导入失败，先尝试通过 sys.path 加载
import importlib, sys, os
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)
import config
from data_fetcher import get_limit_up_filter, get_stock_kline, get_valuation_snapshot


# ============================================================
# 第一部分：情绪龙头（原有逻辑，保留作情绪信号）
# ============================================================

def screen_dragon_stocks_from_hot_sector(sector_data, limit=config.STOCK_WATCH_N):
    stocks = sector_data.get("stocks", [])
    stock_names = sector_data.get("stock_names", [])
    if not stocks:
        return []

    lu_data = get_limit_up_filter(date=datetime.now().strftime("%Y-%m-%d"), limit=200)
    lu_codes = {}
    for lu in lu_data or []:
        c = lu.get("code", "")
        if c:
            lu_codes[c] = lu

    candidates = []
    for i, code in enumerate(stocks):
        name = stock_names[i] if i < len(stock_names) else code
        is_lu = code in lu_codes
        info = lu_codes.get(code, {})

        candidates.append({
            "code": code, "name": name,
            "is_limit_up_today": is_lu,
            "continue_num": info.get("continue_num", 1) if is_lu else 0,
            "reason_type": info.get("reason_type", "") if is_lu else "",
            "close_pct_chg": info.get("changePercent", 0) if is_lu else 0,
        })

    has_lu = [c for c in candidates if c.get("is_limit_up_today")]
    no_lu = [c for c in candidates if not c.get("is_limit_up_today")]
    has_lu.sort(key=lambda x: x.get("continue_num", 0), reverse=True)
    ranked = has_lu + no_lu

    dragons = []
    for s in ranked:
        is_lu = s.get("is_limit_up_today", False)
        cn = s.get("continue_num", 0)
        rt = s.get("reason_type", "")
        score = 0
        rank = "观察"
        if is_lu:
            score += 25
            score += min(cn * 10, 30)
        if rt:
            score += 20
        if score >= 35:
            rank = "核心龙头"
        elif score >= 20:
            rank = "候选龙头"
        else:
            rank = "观察"
        dragons.append({
            "code": s["code"], "name": s["name"],
            "market_cap_yi": None,
            "dragon_score": score,
            "dragon_rank": rank,
            "is_limit_up_today": is_lu,
            "continue_num": cn,
            "reason_type": rt,
            "q1_large_cap": False,
            "q2_recognition": is_lu,
            "q3_logic": bool(rt),
        })

    has_ranked = [d for d in dragons if d["dragon_rank"] in ("核心龙头", "候选龙头")]
    observers = [d for d in dragons if d["dragon_rank"] == "观察"]
    result = has_ranked + observers
    return result[:limit]


def screen_all_mainline_dragons(mainline_sectors, limit_per_sector=3):
    all_dragons = []
    for sector in mainline_sectors:
        dragons = screen_dragon_stocks_from_hot_sector(sector, limit=limit_per_sector)
        all_dragons.append({
            "sector_name": sector["name"],
            "sector_rps": {
                "rps_10": sector.get("rps_10"),
                "rps_20": sector.get("rps_20"),
                "rps_60": sector.get("rps_60"),
            },
            "three_resonance": sector.get("three_resonance"),
            "dragons": dragons,
        })
    return all_dragons


# ============================================================
# 第二部分：趋势中军（新增量化筛选）
# ============================================================

def _load_sector_stock_pool(sector_name):
    """加载板块成分股池: 涨停池+强势股池全量合并 → hot_sectors缓存 → 内置补充"""
    import json, os

    pool = []
    seen_codes = set()
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

    # 1. 涨停池 + 强势股池 → 按行业提取全量成分股
    sector_stocks = _fetch_sector_industry_stocks(cache_dir, sector_name)
    for item in sector_stocks:
        code = item.get("code", "")
        name = item.get("name", "")
        if code and code not in seen_codes:
            seen_codes.add(code)
            pool.append({"code": code, "name": name})

    # 2. hot_sectors 缓存补充
    hs_path = os.path.join(cache_dir, "hotsectors_%s.json" % datetime.now().strftime("%Y-%m-%d"))
    if os.path.exists(hs_path):
        with open(hs_path, "r", encoding="utf-8") as f:
            hs_data = json.load(f)
        for sec in hs_data:
            if sector_name in sec.get("name", ""):
                for s in sec.get("stocks", []):
                    code = s.get("code", "") if isinstance(s, dict) else ""
                    name = s.get("name", "") if isinstance(s, dict) else ""
                    if code and code not in seen_codes:
                        seen_codes.add(code)
                        pool.append({"code": code, "name": name})

    # 3. 内置补充池
    fallback_pools = {
        "专精特新": [ ("300124","汇川技术"), ("300450","先导智能"), ("688017","绿的谐波"),
                      ("002709","天赐材料"), ("300037","新宙邦"),   ("603236","移远通信"),
                      ("688308","欧科亿"),   ("688059","华锐精密") ],
        "商业航天": [ ("600118","中国卫星"), ("600879","航天电子"), ("002025","航天电器"),
                      ("601698","中国卫通"), ("600391","航发科技"), ("688568","中科星图") ],
        "机器人概念": [ ("300124","汇川技术"), ("688017","绿的谐波"), ("002747","埃斯顿"),
                        ("300607","拓斯达") ],
    }
    for key, stocks in fallback_pools.items():
        if key in sector_name or sector_name in key:
            for c, n in stocks:
                if c not in seen_codes:
                    seen_codes.add(c)
                    pool.append({"code": c, "name": n})

    # 4. industry_chain_stocks.json 链式补充
    chain_path = os.path.join(cache_dir, "industry_chain_stocks.json")
    target = None
    if "芯片" in sector_name or "半导体" in sector_name: target = "芯片概念"
    elif "新能源" in sector_name: target = "新能源汽车"
    elif "光伏" in sector_name: target = "光伏概念"
    if target and os.path.exists(chain_path):
        with open(chain_path, "r", encoding="utf-8") as f:
            chain_data = json.load(f)
        for item in chain_data.get(target, []):
            c = item.get("code", "") if isinstance(item, dict) else item[0] if isinstance(item, (list, tuple)) else ""
            n = item.get("name", "") if isinstance(item, dict) else item[1] if isinstance(item, (list, tuple)) else ""
            if c and c not in seen_codes:
                seen_codes.add(c)
                pool.append({"code": c, "name": n})

    return pool


def _fetch_sector_industry_stocks(cache_dir, sector_name):
    """获取板块成分股：涨停池按行业分组 + 内置补充"""
    rows = []

    # 1. 涨停池按行业分组
    try:
        lu_data = get_limit_up_filter(limit=300)
        if lu_data:
            for lu in lu_data:
                ind = lu.get("industry", "") or ""
                nm = lu.get("name", "")
                code = lu.get("code", "")
                if code and (sector_name in ind or ind in sector_name):
                    already = any(item["code"] == code for item in rows)
                    if not already:
                        rows.append({"code": code, "name": nm, "industry": ind, "source": "涨停池"})
    except:
        pass

    # 2. 超过100只则截取（趋势中军只看前排）
    if len(rows) > 100:
        rows = rows[:100]

    # 3. 仍然不足时用内置补充池
    if len(rows) < 15:
        extra = _get_fallback_stocks(sector_name)
        for item in extra:
            c, n = item
            if c not in {r["code"] for r in rows}:
                rows.append({"code": c, "name": n, "industry": sector_name, "source": "内置补充"})

    return rows


def _get_fallback_stocks(sector_name):
    """内置补充：关键板块的已知代表性股票"""
    pools = {
        "芯片": ["688981", "中芯国际", "603501", "韦尔股份", "002371", "北方华创",
                "300661", "圣邦股份", "688012", "中微公司", "603986", "兆易创新"],
        "半导体": ["688981", "中芯国际", "603501", "韦尔股份", "002371", "北方华创",
                  "300661", "圣邦股份", "688012", "中微公司", "603986", "兆易创新"],
        "机器人": ["300124", "汇川技术", "688017", "绿的谐波", "002747", "埃斯顿",
                  "300607", "拓斯达", "688160", "步科股份"],
        "汽车": ["002594", "比亚迪", "600104", "上汽集团", "000625", "长安汽车",
                "601238", "广汽集团", "600733", "北汽蓝谷"],
        "化学制品": ["600309", "万华化学", "002601", "龙佰集团", "600352", "浙江龙盛",
                    "600426", "华鲁恒升", "000830", "鲁西化工"],
        "光学光电": ["002475", "立讯精密", "601138", "工业富联", "002241", "歌尔股份",
                    "300433", "蓝思科技", "603160", "汇顶科技"],
        "通信设备": ["000063", "中兴通讯", "002396", "星网锐捷", "300502", "新易盛",
                    "688036", "传音控股", "300308", "中际旭创"],
        "券商": ["600030", "中信证券", "601066", "中信建投", "600837", "海通证券",
                "601211", "国泰君安", "000776", "广发证券"],
        "医药": ["600276", "恒瑞医药", "300760", "迈瑞医疗", "000538", "云南白药",
                "300015", "爱尔眼科", "603259", "药明康德"],
        "新能源": ["300750", "宁德时代", "002074", "国轩高科", "300014", "亿纬锂能",
                   "601012", "隆基绿能", "600438", "通威股份"],
        "创新药": ["603259", "药明康德", "300347", "泰格医药", "002821", "凯莱英",
                   "688180", "君实生物", "300122", "智飞生物"],
    }
    stock_map = {}
    for key, vals in pools.items():
        if key in sector_name or sector_name in key:
            for i in range(0, len(vals), 2):
                stock_map[vals[i]] = vals[i+1]
    return list(stock_map.items())


def _get_market_cap(code):
    """获取流通市值（亿），从涨停池/悟道估值API"""
    # 1. 涨停池中有流通市值
    lu = get_limit_up_filter(limit=300)
    for item in lu or []:
        if item.get("code", "") == code:
            cv = item.get("currency_value", 0) or item.get("circ_mv", 0) or 0
            if cv > 0:
                return round(cv / 1e8, 1)
    # 2. 悟道估值API（可能不可用）
    vs = get_valuation_snapshot(code)
    if vs:
        cap = vs.get("circ_mv") or vs.get("circMarketCap") or vs.get("market_cap") or 0
        if cap:
            return round(cap / 1e8, 1)
    return None


def _get_5d_avg_amount(code):
    """获取5日均成交额（亿），从K线数据计算"""
    klines = get_stock_kline(code, days=10)
    if klines and len(klines) >= 5:
        amounts = [k.get("amount", 0) for k in klines[-5:] if k.get("amount")]
        if amounts:
            return round(sum(amounts) / len(amounts) / 1e8, 1)
    return None


def _check_ma20_status(code):
    """
    检查MA20状态:
    Returns (price_above_ma20, ma20_direction_up, distance_pct, current_price, ma20_value)
    """
    klines = get_stock_kline(code, days=30)
    if not klines or len(klines) < 25:
        return False, False, None, None, None

    closes = [k["close"] for k in klines]
    latest_price = closes[-1]

    ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    if ma20 is None:
        return False, False, None, latest_price, None

    ma20_5ago = sum(closes[-25:-5]) / 20 if len(closes) >= 25 else ma20
    ma20_slope = (ma20 - ma20_5ago) / ma20_5ago if ma20_5ago else 0

    distance_pct = round((latest_price / ma20 - 1) * 100, 2)
    above = latest_price > ma20
    up = ma20_slope > 0

    return above, up, distance_pct, latest_price, round(ma20, 2)


def _check_pullback_pattern(code):
    """
    检测最近5日内是否有"缩量回踩5/10日线后再次创新高"走势
    返回 (has_pattern, pattern_score, detail)
    """
    klines = get_stock_kline(code, days=30)
    if not klines or len(klines) < 15:
        return False, 0, "数据不足"

    closes = [k["close"] for k in klines]
    volumes = [k.get("volume", 0) for k in klines]
    highs = [k.get("high", k["close"]) for k in klines]

    if len(closes) < 13:
        return False, 0, "数据不足"

    ma5_list = []
    ma13_list = []
    for i in range(len(closes)):
        if i >= 4:
            ma5 = sum(closes[i-4:i+1]) / 5
        else:
            ma5 = sum(closes[:i+1]) / (i+1)
        ma5_list.append(ma5)

        if i >= 12:
            ma13 = sum(closes[i-12:i+1]) / 13
        else:
            ma13 = sum(closes[:i+1]) / (i+1)
        ma13_list.append(ma13)

    last_5 = closes[-5:]
    recent_high = max(highs[-10:-5]) if len(highs) >= 10 else max(closes[:-5]) if len(closes) > 5 else 0

    score = 0
    details = []

    for i in range(-5, 0):
        if abs(i) > len(closes):
            continue
        idx = len(closes) + i
        near_ma5 = abs(closes[idx] / ma5_list[idx] - 1) <= config.TREND_LEADER_NEAR_MA_THRESHOLD
        near_ma13 = abs(closes[idx] / ma13_list[idx] - 1) <= config.TREND_LEADER_NEAR_MA_THRESHOLD
        vol_shrink = (volumes[idx] / (sum(volumes[max(0,idx-5):idx]) / max(idx, 1))) < config.TREND_LEADER_VOLUME_SHRINK if idx > 0 and sum(volumes[max(0,idx-5):idx]) > 0 else False

        if near_ma5 and vol_shrink:
            score += 20
            details.append("缩量回踩MA5")
        elif near_ma13 and vol_shrink:
            score += 15
            details.append("缩量回踩MA13")

    if closes[-1] >= recent_high * 0.98:
        score += 10
        details.append("接近/创近期新高")

    if ma5_list[-1] > ma13_list[-1]:
        score += 5
        details.append("MA5>MA13多头")

    has_pattern = score >= 15
    return has_pattern, min(score, 35), ";".join(details) if details else "未检测到回踩形态"


_lu_cache = None

def _get_continue_num(code):
    global _lu_cache
    if _lu_cache is None:
        _lu_cache = get_limit_up_filter(date=datetime.now().strftime("%Y-%m-%d"), limit=300)
    for lu in _lu_cache or []:
        if lu.get("code", "") == code:
            return lu.get("continue_num", 0)
    return 0


def _classify_ma_form(closes, ma5_list, ma13_list, ma20):
    if len(closes) < 13:
        return "数据不足"

    latest = closes[-1]
    ma5 = ma5_list[-1]
    ma13 = ma13_list[-1]
    high_5 = max(closes[-5:])
    low_5 = min(closes[-5:])

    if latest > ma5 > ma13 > ma20 and latest >= high_5:
        return "强势上攻"

    amplitude = (high_5 - low_5) / low_5
    if latest > ma20 and amplitude < 0.05 and ma5 > ma13:
        return "高位横盘"

    near_ma13 = abs(latest / ma13 - 1) < 0.03
    if near_ma13 and latest > ma20:
        return "缩量回调"

    if latest > ma20:
        return "强势上攻" if ma5 > ma13 else "高位横盘"
    else:
        return "破位调整"


def _check_industry_position(code, name, sector_name):
    """行业地位判断，基于reason_type和sector_name关键词"""
    position_score = 5  # 基础分
    reasons = []

    # 通过涨停原因关键词判断
    lu_data = get_limit_up_filter(date=datetime.now().strftime("%Y-%m-%d"), limit=200)
    for lu in lu_data or []:
        if lu.get("code", "") == code:
            rt = (lu.get("reason_type") or "") + (lu.get("comment") or "")
            if "龙头" in rt:
                position_score += 10
                reasons.append("龙头地位确认")
            if "核心" in rt or "供应商" in rt:
                position_score += 5
                reasons.append("核心供应商")
            if "市占率" in rt or "份额" in rt:
                position_score += 5
                reasons.append("高市占率")
            break

    # 板块龙头加分
    sector_leader_keywords = ["半导体设备", "芯片设计", "封测", "材料", "IDM"]
    if any(kw in (sector_name or "") for kw in sector_leader_keywords):
        position_score += 3

    return min(position_score, 15), ";".join(reasons) if reasons else "细分龙头"


def _compute_trend_leader_score(market_cap, amount_5d, ma_distance, pattern_score, industry_score):
    """综合评分"""
    w = config.TREND_LEADER_WEIGHTS

    score = 0

    if market_cap and market_cap >= config.TREND_LEADER_MIN_CIRC_MARKET_YI:
        cap_score = min((market_cap - 100) / 10, 20)
        score += cap_score

    if amount_5d and amount_5d >= config.TREND_LEADER_MIN_AMOUNT_5D_YI:
        amt_score = min((amount_5d - 5) / 2, 20)
        score += amt_score

    if ma_distance is not None:
        ma_score = min(ma_distance * 2, 20)
        score += ma_score

    score += pattern_score
    score += industry_score

    return round(score, 0)


def screen_trend_leaders(sector_names, limit_per_sector=3):
    """
    趋势中军筛选主函数

    参数:
        sector_names: list[str] 板块名称列表
        limit_per_sector: int 每个板块最多返回几只

    返回:
        list[dict] 每个板块的筛选结果
    """
    if isinstance(sector_names, str):
        sector_names = [sector_names]

    results = []

    for sector_name in sector_names:
        pool = _load_sector_stock_pool(sector_name)
        if not pool:
            results.append({
                "sector_name": sector_name,
                "sector_rps": {},
                "three_resonance": False,
                "trend_leaders": [],
                "note": "无本地成分股数据，请使用API获取",
            })
            continue

        scored = []
        for item in pool:
            code = item["code"]
            name = item["name"]

            # 1. 拒绝连板情绪票
            cn = _get_continue_num(code)
            if cn >= config.TREND_LEADER_REJECT_CONTINUE:
                continue

            # 2. 流通市值检查
            market_cap = _get_market_cap(code)

            # 3. 5日均成交额检查
            amount_5d = _get_5d_avg_amount(code)

            # 4. MA20状态检查
            above_ma20, ma20_up, ma_distance, cur_price, ma20_val = _check_ma20_status(code)

            # 5. 回踩形态检测
            has_pattern, pattern_score, pattern_detail = _check_pullback_pattern(code)
            # 距MA20太远不视为当前有效回踩
            if ma_distance is not None and abs(ma_distance) > 12:
                has_pattern = False
                pattern_score = 0

            # 6. 行业地位
            industry_score, industry_detail = _check_industry_position(code, name, sector_name)

            # 达标判断
            cap_pass = market_cap is None or market_cap >= config.TREND_LEADER_MIN_CIRC_MARKET_YI
            amt_pass = amount_5d is None or amount_5d >= config.TREND_LEADER_MIN_AMOUNT_5D_YI
            trend_pass = above_ma20 and ma20_up
            fails = []

            if market_cap is not None and not cap_pass:
                fails.append("市值%.0f亿<门槛(%d亿)" % (market_cap, config.TREND_LEADER_MIN_CIRC_MARKET_YI))
            if amount_5d is not None and not amt_pass:
                fails.append("成交额%.1f亿<门槛(%d亿)" % (amount_5d, config.TREND_LEADER_MIN_AMOUNT_5D_YI))
            if not trend_pass and ma20_val is not None:
                fails.append("MA20未达标")
            if cn >= config.TREND_LEADER_REJECT_CONTINUE:
                fails.append("%d连板情绪票" % cn)

            # 综合评分
            total_score = _compute_trend_leader_score(
                market_cap, amount_5d, ma_distance,
                pattern_score, industry_score
            )

            # 形态分类
            klines = get_stock_kline(code, days=30)
            ma_form = "数据不足"
            if klines and len(klines) >= 10:
                closes = [k["close"] for k in klines]
                ma5 = [sum(closes[max(0,i-4):i+1])/min(5,i+1) for i in range(len(closes))]
                ma13 = [sum(closes[max(0,i-12):i+1])/min(13,i+1) for i in range(len(closes))]
                ma20_list = [sum(closes[max(0,i-19):i+1])/min(20,i+1) for i in range(len(closes))]
                ma_form = _classify_ma_form(closes, ma5, ma13, ma20_list[-1])

            scored.append({
                "code": code, "name": name,
                "market_cap_yi": market_cap,
                "amount_5d_yi": amount_5d,
                "above_ma20": above_ma20,
                "ma20_up": ma20_up,
                "ma_distance_pct": ma_distance,
                "current_price": cur_price,
                "ma20_value": ma20_val,
                "continue_num": cn,
                "has_pullback_pattern": has_pattern,
                "pattern_score": pattern_score,
                "pattern_detail": pattern_detail,
                "industry_score": industry_score,
                "industry_detail": industry_detail,
                "ma_form": ma_form,
                "total_score": total_score,
                "cap_pass": cap_pass,
                "amt_pass": amt_pass,
                "trend_pass": trend_pass,
                "fails": fails,
                "qualified": cap_pass and amt_pass and trend_pass and cn < config.TREND_LEADER_REJECT_CONTINUE,
            })

        # 排序：达标的按评分降序，未达标的排在后面
        qualified = [s for s in scored if s["qualified"]]
        unqualified = [s for s in scored if not s["qualified"]]
        qualified.sort(key=lambda x: x["total_score"], reverse=True)
        unqualified.sort(key=lambda x: x["total_score"], reverse=True)

        results.append({
            "sector_name": sector_name,
            "sector_rps": {},
            "three_resonance": False,
            "total_candidates": len(pool),
            "qualified_count": len(qualified),
            "trend_leaders": (qualified + unqualified)[:limit_per_sector * 2],
        })

    return results


# ============================================================
# 公共接口（简报使用）
# ============================================================

def screen_all_mainline_trend_leaders(mainline_sectors, limit_per_sector=3, top_k=3):
    """
    对所有主线板块执行趋势中军筛选（只取评分前top_k个板块）
    """
    if not mainline_sectors:
        return []

    # 只取涨停数最多的前 top_k 个板块
    ranked_sectors = sorted(mainline_sectors,
                            key=lambda x: x.get("limit_up_num", 0), reverse=True)
    top_sectors = ranked_sectors[:top_k]
    sector_names = [s["name"] for s in top_sectors]

    # 构建 sector_rps 映射
    rps_map = {}
    for s in top_sectors:
        rps_map[s["name"]] = {
            "rps_10": s.get("rps_10"),
            "rps_20": s.get("rps_20"),
            "rps_60": s.get("rps_60"),
            "three_resonance": s.get("three_resonance"),
            "limit_up_num": s.get("limit_up_num", 0),
        }

    results = screen_trend_leaders(sector_names, limit_per_sector)
    for r in results:
        info = rps_map.get(r["sector_name"], {})
        r["sector_rps"] = {
            "rps_10": info.get("rps_10"),
            "rps_20": info.get("rps_20"),
            "rps_60": info.get("rps_60"),
        }
        r["three_resonance"] = info.get("three_resonance", False)
        r["limit_up_num"] = info.get("limit_up_num", 0)

    return results
