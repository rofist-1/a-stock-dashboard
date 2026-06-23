# -*- coding: utf-8 -*-
"""
悟道 A 股数据 API 客户端
========================
共享模块，封装 HTTP 请求，供 chain_analysis.py / bugu_monitor.py 等调用。

API 文档: https://stock.quicktiny.cn/api/openclaw
"""

import os
import json
import time
from datetime import datetime

import requests

BASE_URL = "https://stock.quicktiny.cn/api/openclaw"
API_KEY = "lb_ace63359b2c36bf7f71a070f89f9717f8434a287fe8a914e69b4b4d780424e97"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

_REQUEST_INTERVAL = 0.35  # 限流间隔(秒)
_last_call = 0.0


def _rate_limit():
    global _last_call
    now = time.time()
    gap = now - _last_call
    if gap < _REQUEST_INTERVAL:
        time.sleep(_REQUEST_INTERVAL - gap)
    _last_call = time.time()


def _get(endpoint: str, params: dict = None) -> dict:
    _rate_limit()
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def get_limit_up_filter(date: str, limit: int = 200) -> list:
    """
    获取指定日期的涨停股票列表（含涨停原因、连板数、行业等）。

    Parameters
    ----------
    date : str, YYYYMMDD or YYYY-MM-DD
    limit : int, default 200

    Returns
    -------
    list[dict] : [{code, name, continue_num, reason_type, industry, change_rate, ...}]
        字段为 snake_case: code, name, continue_num, reason_type, industry,
        change_rate, order_amount, order_volume, first_limit_up_time,
        last_limit_up_time, open_num, limit_up_type, trading_amount,
        currency_value, total_market_cap, turnover_rate, 等。
    """
    resp = _get("limit-up/filter", {"date": date, "limit": limit})
    if resp.get("success"):
        data = resp.get("data", {})
        return data.get("items", [])
    return []


def get_limit_stats(date: str) -> dict:
    """
    涨跌停统计（封板数、炸板数、封板率等）。

    Returns
    -------
    dict : {sealedLimitUp, touchedLimitUp, brokenLimitUp, limitUpSealRate, ...}
    """
    resp = _get("limit-stats", {"date": date})
    if resp.get("success"):
        return resp.get("data", {})
    return {}


def get_hot_sectors(date: str) -> list:
    """
    最强风口（按涨停集中度排名的板块列表）。

    Returns
    -------
    list[dict] : [{name, limitUpNum, continuousPlateNum, highBoard, stocks, ...}]
    """
    resp = _get("hot-sectors", {"date": date})
    if resp.get("success"):
        data = resp.get("data", [])
        return data if isinstance(data, list) else []
    return []


def get_broken_limit_up(date: str) -> list:
    """
    炸板池（盘中触及涨停但未封住的股票）。

    Returns
    -------
    list[dict] : [{code, name, changePercent, openNum, reasonType, ...}]
    """
    resp = _get("broken-limit-up", {"date": date})
    if resp.get("success"):
        data = resp.get("data", {})
        return data.get("stocks", []) if isinstance(data, dict) else []
    return []


def get_limit_down(date: str) -> list:
    """
    跌停池。

    Returns
    -------
    list[dict]
    """
    resp = _get("limit-down", {"date": date})
    if resp.get("success"):
        data = resp.get("data", {})
        return data.get("stocks", []) if isinstance(data, dict) else []
    return []


def get_ladder(date: str) -> list:
    """
    涨停梯队（连板高度及每层个股详情）。

    Returns
    -------
    list[dict] : [{level, stocks: [...]}, ...]
    """
    resp = _get("ladder", {"date": date})
    if resp.get("success"):
        data = resp.get("data", {})
        dates_data = data.get("dates", [])
        if dates_data:
            return dates_data[0].get("boards", [])
        return []
    return []


def get_market_overview(date: str) -> dict:
    """
    市场概况。

    Returns
    -------
    dict : {rise_count, fall_count, limit_up_count, limit_down_count, market_temperature, ...}
    """
    resp = _get("market-overview", {"date": date})
    if resp.get("success"):
        return resp.get("data", {})
    return {}


def search_stock(query: str, limit: int = 10) -> list:
    """
    搜索股票（名称/代码/拼音）。

    Returns
    -------
    list[dict]
    """
    resp = _get("search", {"query": query, "limit": limit})
    if resp.get("success"):
        return resp.get("data", {}).get("items", [])
    return []


def get_stock_screener(params: dict) -> list:
    """
    条件选股。传入结构化筛选条件。

    Parameters
    ----------
    params : dict
        支持 conceptKeywords, industryKeywords, aboveMa, volumeRatioMin,
        closePctChgMin, priceMin, marketCapMinYi, areaKeywords, nameIncludes 等。

    Returns
    -------
    list[dict]
    """
    resp = _get("stock-screener", params)
    if resp.get("success"):
        return resp.get("data", {}).get("rows", [])
    return []


def get_financial_summary(code: str, limit: int = 4) -> dict:
    """
    个股基本面摘要（营收构成、利润、ROE 等）。

    Returns
    -------
    dict : {revenue_breakdown, segments, ...}
    """
    resp = _get("financial-summary", {"code": code, "limit": limit})
    if resp.get("success"):
        return resp.get("data", {})
    return {}


def get_concept_ranking(limit: int = 20) -> list:
    """
    概念板块涨幅/涨停数排行。

    Returns
    -------
    list[dict] : [{name, ts_code, change, limit_up_num, ...}]
    """
    resp = _get("concept-ranking", {"limit": limit})
    if resp.get("success"):
        return resp.get("data", {}).get("items", [])
    return []


def get_concept_stocks(ts_code: str) -> list:
    """
    指定概念板块的成分股。

    Returns
    -------
    list[dict] : [{code, name, ...}]
    """
    resp = _get("concept-stocks", {"tsCode": ts_code})
    if resp.get("success"):
        return resp.get("data", {}).get("items", [])
    return []


def get_valuation_snapshot(code: str) -> dict:
    """
    个股估值快照（PE/PB/市值/换手率等）。

    Returns
    -------
    dict
    """
    resp = _get("valuation-snapshot", {"code": code})
    if resp.get("success"):
        return resp.get("data", {})
    return {}


if __name__ == "__main__":
    today = datetime.now().strftime("%Y%m%d")
    print(f"[TEST] 测试悟道 API 客户端 ({today})...")

    stats = get_limit_stats(today)
    print(f"  涨停: {stats.get('sealedLimitUp', '?')} / 炸板: {stats.get('brokenLimitUp', '?')} / 封板率: {stats.get('limitUpSealRate', '?')}")

    stocks = get_limit_up_filter(today, limit=5)
    print(f"  涨停股票(前5): {[s['name'] for s in stocks]}")

    sectors = get_hot_sectors(today)
    print(f"  最强风口: {[s['name'] for s in sectors[:5]]}")

    print("[TEST OK]")
