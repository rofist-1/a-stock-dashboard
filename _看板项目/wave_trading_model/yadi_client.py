# -*- coding: utf-8 -*-
"""
雅迪 A 股数据 API 客户端
=======================
API 基础地址: https://api.cxdy.vip/api/
Token 参数名: apiToken
"""

import os, json, time, requests
from datetime import datetime

BASE_URL = "https://api.cxdy.vip/api"
API_TOKEN = "4377183a3f71a9eda95741cd2eb8e6a944c6fe90"

_REQUEST_INTERVAL = 0.5
_last_call = 0.0

def _rate_limit():
    global _last_call
    now = time.time()
    gap = now - _last_call
    if gap < _REQUEST_INTERVAL:
        time.sleep(_REQUEST_INTERVAL - gap)
    _last_call = time.time()

def _get(endpoint, params=None):
    _rate_limit()
    p = {"apiToken": API_TOKEN}
    if params:
        p.update(params)
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    r = requests.get(url, params=p, timeout=30)
    r.raise_for_status()
    return r.json()

def get_stock_list():
    """hslb - 全部股票列表"""
    return _get("hslb")

def get_kline(code, start_date, end_date=None, adjust="qfq"):
    """lsjy - 历史K线, symbol=sh/sz+code, adjust=qfq"""
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")
    return _get("lsjy", {
        "symbol": code,
        "adjust": adjust,
        "start_date": start_date,
        "end_date": end_date,
    })

def get_realtime():
    """ssjy - 实时行情"""
    return _get("ssjy")

def get_concept_sectors():
    """bkzj - 概念板块资金流向"""
    return _get("bkzj")

def get_company_detail(code):
    """gsxq - 公司详情（含行业）"""
    return _get("gsxq", {"code": code})

def get_commentary(code):
    """qgqp - 千股千评（含换手率/市盈率）"""
    return _get("qgqp", {"code": code})

if __name__ == "__main__":
    today = datetime.now().strftime("%Y%m%d")
    print("[TEST] 雅迪 API 测试...")

    # 1. 股票列表
    stocks = get_stock_list()
    print(f"  hslb: {len(stocks) if isinstance(stocks,list) else '?'} 只股票")

    # 2. 概念板块
    sectors = get_concept_sectors()
    if isinstance(sectors, list):
        print(f"  bkzj: {len(sectors)} 个板块")
        for s in sectors[:5]:
            print(f"    {s.get('name','?')}  {s.get('changePercent','')}%")
    else:
        print(f"  bkzj: {str(sectors)[:200]}")

    # 3. K线测试
    kline = get_kline("sh600519", "20260601", "20260630")
    if isinstance(kline, list):
        print(f"  lsjy(贵州茅台): {len(kline)} 条K线")
    else:
        print(f"  lsjy: {str(kline)[:200]}")

    print("[TEST OK]")
