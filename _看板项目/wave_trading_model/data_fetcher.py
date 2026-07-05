"""
数据获取层
==========
三源策略: 雅迪API(付费优先) → 雅迪API(备用) → AKShare(免费备用)

路径规划:
  全部优先走雅迪，降级悟道和AKShare
"""

import os, sys, json, time
from datetime import datetime, timedelta

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(MODULE_DIR)
CACHE_DIR = os.path.join(MODULE_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

WUDAO_PATH = os.path.join(BASE_DIR, "百日新高系统", "wudao_client.py")
YADI_PATH = os.path.join(MODULE_DIR, "yadi_client.py")

# ======================== 雅迪API (主数据源) ========================
_yadi = None
def _get_yadi():
    global _yadi
    if _yadi is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("yadi_client", YADI_PATH)
        if spec is None: return None
        _yadi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_yadi)
    return _yadi

# ======================== 悟道API (降级备用) ========================
_wudao = None
def _get_wudao():
    global _wudao
    if _wudao is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("wudao_client", WUDAO_PATH)
        if spec is None: return None
        _wudao = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_wudao)
    return _wudao

_last_call = 0.0
_REQ_INTERVAL = 0.5
def _rl():
    global _last_call
    now = time.time()
    gap = now - _last_call
    if gap < _REQ_INTERVAL: time.sleep(_REQ_INTERVAL - gap)
    _last_call = time.time()

def _call_yadi(endpoint, params=None):
    _rl()
    y = _get_yadi()
    if y is None: return None
    try:
        if endpoint == "concept_sectors":
            return y.get_concept_sectors()
        elif endpoint == "kline":
            return y.get_kline(params.get("code"), params.get("start_date"), params.get("end_date"))
        elif endpoint == "company_detail":
            return y.get_company_detail(params.get("code"))
        elif endpoint == "commentary":
            return y.get_commentary(params.get("code"))
    except Exception as e:
        return None
    return None

def _call_wudao(endpoint, params=None):
    _rl()
    w = _get_wudao()
    if w is None: return None
    fn_map = {
        "kline": lambda: w.get_kline(params.get("code"), params.get("days"), params.get("endDate")),
        "market_overview": lambda: w.get_market_overview(params.get("date")),
        "hot_sectors": lambda: w.get_hot_sectors(params.get("date")),
        "limit_up_filter": lambda: w.get_limit_up_filter(params.get("date"), params.get("limit", 200)),
        "stock_screener": lambda: w.get_stock_screener(params),
    }
    fn = fn_map.get(endpoint)
    if not fn:
        return None
    try:
        return fn()
    except Exception as e:
        return None

# ======================== 缓存 ========================
def _cached(name, max_age_hours, fetch_fn):
    path = os.path.join(CACHE_DIR, f"{name}.json")
    if os.path.exists(path):
        age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(path))
        if age.total_seconds() <= max_age_hours * 3600:
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
    data = fetch_fn()
    if data:
        with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    return data

# ======================== 公开API (雅迪→悟道) ========================

def get_index_kline(code="000001.SH", days=65):
    """获取指数K线。优先读index_kline_history.json缓存，其次悟道（需验证非股票数据）"""
    # 1. 读本地历史缓存
    hist = _read_index_kline_cache()
    if len(hist) >= days:
        return hist[-days:] if days else hist
    # 2. 尝试悟道K-line（可能返回股票数据，需验证）
    data = _call_wudao("kline", {"code": code, "days": days})
    if data and isinstance(data, list) and len(data) > 1:
        closes = [k.get("close", 0) for k in data if k.get("close")]
        avg = sum(closes) / len(closes) if closes else 0
        # SSE指数应在3000点左右，股票000001约10元，用200做阈值
        if avg > 200:
            return data
    # 3. 合并缓存（可能只有几天）
    if hist:
        return hist
    # 4. 使用快照值 + market_overview进行估算
    return _cached(f"ikline_{code}_{days}", 24, lambda: [])

def _read_index_kline_cache():
    path = os.path.join(CACHE_DIR, "index_kline_history.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                return data
    except:
        pass
    return []

def _append_index_kline_cache(kline):
    path = os.path.join(CACHE_DIR, "index_kline_history.json")
    existing = _read_index_kline_cache()
    dates = {k["date"] for k in existing if "date" in k}
    for k in kline if isinstance(kline, list) else [kline]:
        d = k.get("date", "")
        if d and d not in dates:
            existing.append(k)
            dates.add(d)
    existing.sort(key=lambda x: x.get("date", ""))
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except:
        pass
    return existing

def get_stock_kline(code, days=65, end_date=None):
    data = _call_wudao("kline", {"code": code, "days": days, "endDate": end_date})
    if data: return data
    return _cached(f"skline_{code}_{days}_{end_date or ''}", 24, lambda: [])

def get_market_overview(date=None):
    if date is None: date = datetime.now().strftime("%Y-%m-%d")
    return _cached(f"mov_{date}", 0.5,
                   lambda: _call_wudao("market_overview", {"date": date}))

# --- 涨停事件池: 雅迪API → 悟道API ---
def get_limit_up_filter(date=None, limit=200):
    if date is None: date = datetime.now().strftime("%Y-%m-%d")
    data = _call_wudao("limit_up_filter", {"date": date, "limit": limit})
    if data: return data
    return _cached(f"luf_{date}", 0.5, lambda: [])

# --- 概念板块: 雅迪API → 悟道API ---
def get_hot_sectors(date=None):
    if date is None: date = datetime.now().strftime("%Y-%m-%d")

    # 1. 雅迪API概念板块
    data = _call_yadi("concept_sectors")
    if data and isinstance(data, dict) and data.get("code") == 200:
        rows = data.get("data", [])
        sectors = []
        for r in rows[:40]:
            sectors.append({
                "name": r.get("\u677f\u5757\u540d\u79f0", "").replace("\u6982\u5ff5", ""),
                "limitUpNum": r.get("\u4e0a\u6da8\u5bb6\u6570", 0),
                "changePercent": r.get("\u6da8\u8dcc\u5e45", 0),
                "stocks": [],
            })
        if sectors:
            _write_cache(f"hotsectors_{date}", sectors)
            return sectors

    # 2. 悟道API
    data = _call_wudao("hot_sectors", {"date": date})
    if data:
        for s in data:
            nm = s.get("name", "")
            if nm.endswith("\u6982\u5ff5"):
                s["name"] = nm[:-2]
        _write_cache(f"hotsectors_{date}", data)
        return data

    return _read_cache(f"hotsectors_{date}")

def _write_cache(name, data):
    path = os.path.join(CACHE_DIR, f"{name}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except: pass

# --- 选股 (仅悟道, 低频) ---
def get_stocks_by_sector(keywords, limit=15):
    params = {"conceptKeywords": keywords, "sortBy": "marketCapYi", "order": "desc", "limit": limit}
    return _call_wudao("stock_screener", params) or []

def screen_stocks(params):
    return _call_wudao("stock_screener", params)

def get_valuation_snapshot(code):
    """估值快照（悟道REST可能不可用，仅返回涨停池数据）"""
    return _cached(f"val_{code}", 4, lambda: {})

def get_financial_summary(code, limit=4):
    return _cached(f"fin_{code}_{limit}", 24, lambda: {})


def clear_cache(max_age_hours=24):
    now = datetime.now(); cleared = 0
    for f in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, f)
        if not f.endswith(".json"): continue
        age = now - datetime.fromtimestamp(os.path.getmtime(path))
        if age.total_seconds() > max_age_hours * 3600: os.remove(path); cleared += 1
    return cleared


# ======================== 市场环境统计（海报参考面板） ========================
def fetch_market_stats(trade_date=None, new_low=0):
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    else:
        trade_date = str(trade_date)[:10]

    result = {
        "date": trade_date,
        "volume_yi": "--",      # 成交量(亿)
        "volume_pct_chg": "--", # 环比
        "limit_up": "--",       # 涨停
        "limit_down": "--",     # 跌停
        "zhadian": "--",        # 炸板
        "lianban": "--",        # 连板
        "new_high": "--",       # 百日新高
        "new_low": new_low,     # 百日新低
        "new_high_diff": "--",
        "new_high_add": "--",
        "fengban_rate": "--",   # 封板率
    }

    try:
        stats = _call_wudao("limit_stats", {"date": trade_date})
        if stats:
            result["limit_up"] = stats.get("limitUp", stats.get("limit_up_count", "--"))
            result["limit_down"] = stats.get("limitDown", stats.get("limit_down_count", "--"))
            fbr = stats.get("sealRate", stats.get("fengban_rate", None))
            if fbr is not None:
                result["fengban_rate"] = f"{float(fbr):.0f}%"
            broken = stats.get("brokenCount", stats.get("zhadian", None))
            if broken is not None:
                result["zhadian"] = broken
    except:
        pass

    try:
        ladder = _call_wudao("limit_up_ladder", {"date": trade_date, "detailLevel": "standard", "limit": 30})
        if ladder:
            total = 0
            for level in ladder if isinstance(ladder, list) else [ladder]:
                cnt = level.get("count", level.get("memberCount", 0)) if isinstance(level, dict) else 0
                total += cnt
            result["lianban"] = total if total > 0 else "--"
    except:
        pass

    return result
