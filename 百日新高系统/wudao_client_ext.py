# -*- coding: utf-8 -*-
"""
Wudao API 客户端扩展
=====================
在 wudao_client.py 基础上补充本系统所需的接口。
"""
import json, urllib.request, urllib.parse, os, time
from datetime import datetime

_API_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.wudao_api_key')
API_KEY = os.environ.get('WUDAO_API_KEY', '')
if not API_KEY:
    try:
        with open(_API_KEY_FILE) as f:
            API_KEY = f.read().strip()
    except:
        pass
API_KEY = API_KEY or ''

BASE_URL = 'https://stock.quicktiny.cn/api/openclaw'
HEADERS = {'Authorization': f'Bearer {API_KEY}'}
_INTERVAL = 0.5
_last_call = 0.0
_MAX_RETRIES = 3

def _rate_limit():
    global _last_call
    now = time.time()
    if now - _last_call < _INTERVAL:
        time.sleep(_INTERVAL - (now - _last_call))
    _last_call = time.time()

def _get(endpoint, params=None):
    for attempt in range(_MAX_RETRIES):
        _rate_limit()
        url = f'{BASE_URL}/{endpoint.lstrip("/")}'
        if params:
            qs = urllib.parse.urlencode(params, encoding='utf-8')
            url = f'{url}?{qs}'
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < _MAX_RETRIES - 1:
                wait = 2 ** attempt
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f'API request failed after {_MAX_RETRIES} attempts')

def request(endpoint, params=None):
    """公共请求入口，返回 data 部分"""
    resp = _get(endpoint, params)
    if isinstance(resp, dict) and resp.get('success'):
        return resp.get('data', {})
    return {}

# ─── 接口封装 ─────────────────────────────────────────

def get_kline(code, days=60, end_date=None):
    """K线数据，返回 list[dict]"""
    params = {'code': code, 'days': days}
    if end_date:
        params['endDate'] = end_date
    data = request('kline', params)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get('rows', data.get('data', []))
    return []

def get_stock_screener(params):
    """条件选股，返回 rows list"""
    data = request('stock-screener', params)
    if isinstance(data, dict):
        return data.get('rows', [])
    if isinstance(data, list):
        return data
    return []

def get_market_overview(date=None):
    """市场概况"""
    params = {}
    if date:
        params['date'] = date
    return request('market-overview', params)

def get_limit_stats(date):
    """涨跌停统计"""
    return request('limit-stats', {'date': date})

def get_limit_up_filter(date, limit=200):
    """涨停列表"""
    data = request('limit-up/filter', {'date': date, 'limit': limit})
    if isinstance(data, dict):
        return data.get('items', [])
    return []

def get_briefings(date, btype='closing'):
    """市场简报"""
    return request('briefings', {'date': date, 'type': btype})

def get_search(query):
    """搜索股票/指数"""
    data = request('search', {'query': query})
    return data.get('items', [])

def get_index_daily(code):
    """获取指数日线行情 (单日)"""
    data = request('index-market', {'code': code, 'mode': 'daily'})
    if isinstance(data, dict):
        rows = data.get('rows', [])
        return rows[0] if rows else None
    return None
