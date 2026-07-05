# -*- coding: utf-8 -*-
"""
每日选股系统 v1.0
==================
数据源：悟道 API
盘后自动运行，输出每日选股简报。

用法：
  python daily_selection_system.py                    # 最新交易日
  python daily_selection_system.py --date 20260630    # 指定日期
  python daily_selection_system.py --output report.md # 输出到文件
"""
import json, os, sys, time, math
from datetime import datetime
from collections import defaultdict, Counter

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from wudao_client_ext import (
    get_kline, get_stock_screener, get_market_overview,
    _get, request
)

# ── 常量 ──────────────────────────────────────────
DATA_DIR = _script_dir
SSE_CACHE_FILE = os.path.join(DATA_DIR, 'sse_cache.json')
DATE_FORMAT = '%Y%m%d'
BATCH_SIZE = 20  # 批量 kline 大小

# ── 辅助函数 ──────────────────────────────────────

def log(msg):
    print(msg)

def parse_date(date_str):
    if not date_str:
        return datetime.now().strftime(DATE_FORMAT)
    return date_str.replace('-', '')

def fmt_date(d):
    s = str(d).replace('-', '')
    return f'{s[:4]}-{s[4:6]}-{s[6:8]}'

def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except:
        return default

def calc_sma(values, n):
    if not values or len(values) < n:
        return None
    return sum(values[-n:]) / n

def calc_ma_direction(values, n, lookback=5):
    ma_now = calc_sma(values, n)
    if not ma_now or len(values) < n + lookback:
        return 'unknown'
    ma_prev = calc_sma(values[:-lookback], n)
    if ma_prev is None:
        return 'unknown'
    chg = (ma_now - ma_prev) / ma_prev * 100
    if chg > 0.3:
        return 'up'
    elif chg < -0.3:
        return 'down'
    return 'flat'

def group_by_industry(rows):
    counter = Counter()
    industry_map = {}
    for r in rows:
        ind = r.get('industry', '') or '未知'
        counter[ind] += 1
        if ind not in industry_map:
            industry_map[ind] = []
        industry_map[ind].append({
            'code': r.get('code', ''),
            'name': r.get('name', ''),
            'closePctChg': safe_float(r.get('closePctChg', 0)),
        })
    return counter, industry_map

# ── Kline 批量缓存 ────────────────────────────────

class KlineCache:
    """批量 Kline 缓存，避免重复请求"""
    def __init__(self):
        self._cache = {}  # code -> klines list
        self._pending = set()

    def fetch_batch(self, codes, days=80):
        """批量获取 kline"""
        needed = [c for c in codes if c not in self._cache]
        if not needed:
            return

        for i in range(0, len(needed), BATCH_SIZE):
            batch = needed[i:i + BATCH_SIZE]
            try:
                resp = _get('kline', {'codes': batch, 'days': days})
                data = resp.get('data', {})
                items = data.get('items', [])
                for item in items:
                    if item.get('ok'):
                        stock = item.get('stock', {})
                        code = stock.get('code', '')
                        rows = item.get('data', [])
                        if code and rows:
                            self._cache[code] = rows
            except Exception as e:
                log(f'  [警告] 批量 kline 失败: {e}')
                time.sleep(2)
            time.sleep(1.5)  # 批间间隔

    def get(self, code, days=80):
        """获取单只 kline"""
        if code not in self._cache:
            self.fetch_batch([code], days)
        return self._cache.get(code, [])


# ═══════════════════════════════════════════════════
# 模块一：大盘环境判断
# ═══════════════════════════════════════════════════

def get_market_environment(date, kcache=None):
    log('[模块一] 判断大盘环境...')

    market = get_market_overview(date)
    market_temp = safe_float(market.get('market_temperature', 50))
    rise = int(market.get('rise_count', 0))
    fall = int(market.get('fall_count', 0))
    total = rise + fall or 1
    rise_ratio = rise / total * 100

    # SSE 缓存（用沪深300作参考）
    sse_cache = []
    if os.path.exists(SSE_CACHE_FILE):
        try:
            with open(SSE_CACHE_FILE, 'r', encoding='utf-8') as f:
                sse_cache = json.load(f)
        except:
            sse_cache = []

    try:
        hs300 = get_kline('000300.SH', 80)
        if hs300:
            for row in hs300:
                d = row.get('date', '')
                if d and len(str(d)) == 8:
                    found = False
                    for item in sse_cache:
                        if item.get('date') == d:
                            item['close'] = safe_float(row.get('close', item.get('close', 0)))
                            found = True
                            break
                    if not found:
                        sse_cache.append({'date': d, 'close': safe_float(row.get('close', 0))})
    except:
        pass

    seen = set()
    sse_cache = sorted(
        [x for x in sse_cache if x.get('date', '') not in seen and len(str(x.get('date', ''))) == 8 and not seen.add(x.get('date', ''))],
        key=lambda x: x.get('date', '')
    )[-120:]

    try:
        with open(SSE_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(sse_cache, f, ensure_ascii=False, indent=2)
    except:
        pass

    closes = [safe_float(x.get('close', 0)) for x in sse_cache if safe_float(x.get('close', 0)) > 0]
    current_close = closes[-1] if closes else 0
    ma20 = calc_sma(closes, 20)
    ma20_dir = calc_ma_direction(closes, 20, 5)

    if ma20 and current_close > ma20 * 1.005 and ma20_dir == 'up':
        market_state = '上涨市'
        position_limit = '7～10成'
        position_note = '积极参与，可追高'
    elif ma20 and current_close < ma20 * 0.995 and ma20_dir == 'down':
        market_state = '下跌市'
        position_limit = '0～1成'
        position_note = '强制空仓或极轻仓试盘'
    else:
        market_state = '震荡市'
        position_limit = '3～5成'
        position_note = '禁止追高，只低吸'

    result = {
        'date': date, 'market_state': market_state,
        'position_limit': position_limit, 'position_note': position_note,
        'current_close': round(current_close, 2) if current_close else 'N/A',
        'ma20': round(ma20, 2) if ma20 else 'N/A',
        'ma20_dir': ma20_dir,
        'market_temperature': round(market_temp, 1),
        'rise_ratio': round(rise_ratio, 1),
        'rise_count': rise, 'fall_count': fall,
    }

    log(f'  市场状态: {market_state}')
    log(f'  仓位上限: {position_limit} ({position_note})')
    log(f'  市场温度: {result["market_temperature"]}°C  涨跌比: {rise}/{fall}')
    return result


# ═══════════════════════════════════════════════════
# 模块二：主线板块锁定
# ═══════════════════════════════════════════════════

def get_sector_rps(date, n_days=10, limit=300):
    """获取行业 RPS 近似值"""
    params = {
        'limit': limit, 'excludeST': 'true',
        'recentNdChgDays': n_days, 'recentNdChgMin': -100,
        'sortBy': 'closePctChg', 'sortOrder': 'desc', 'date': date,
    }
    try:
        stocks = get_stock_screener(params)
    except:
        return {}
    if not stocks:
        return {}

    ind_perf = defaultdict(list)
    for s in stocks:
        ind = s.get('industry', '') or '未知'
        chg = safe_float(s.get('closePctChg', 0))
        ind_perf[ind].append(chg)

    ind_avg = {}
    for ind, chgs in ind_perf.items():
        if len(chgs) >= 3:
            ind_avg[ind] = {'avg_chg': round(sum(chgs) / len(chgs), 2), 'count': len(chgs)}

    sorted_ind = sorted(ind_avg.items(), key=lambda x: -x[1]['avg_chg'])
    total = len(sorted_ind)
    rps = {}
    for rank, (ind, data) in enumerate(sorted_ind):
        rps_val = round((1 - rank / total) * 100, 1) if total > 0 else 0
        rps[ind] = {'rps': rps_val, 'avg_chg': data['avg_chg'], 'count': data['count']}
    return rps


def get_100day_new_high_sectors(date, limit=300):
    """近似统计各行业创新高股票数量"""
    params = {
        'limit': limit, 'excludeST': 'true',
        'recentNdChgDays': 20, 'recentNdChgMin': 15,
        'sortBy': 'closePctChg', 'sortOrder': 'desc', 'date': date,
    }
    try:
        stocks = get_stock_screener(params)
    except:
        return {}
    if not stocks:
        return {}
    counter, _ = group_by_industry(stocks)
    total_stocks = sum(counter.values())
    result = {}
    for ind, cnt in counter.most_common(30):
        result[ind] = {'count': cnt, 'ratio': round(cnt / max(total_stocks, 1) * 100, 1)}
    return result


def lock_main_sectors(date):
    """锁定主线板块"""
    log('[模块二] 锁定主线板块...')

    log('  计算 RPS(10)...')
    rps10 = get_sector_rps(date, 10)
    time.sleep(1.5)
    log('  计算 RPS(20)...')
    rps20 = get_sector_rps(date, 20)
    time.sleep(1.5)
    log('  计算 RPS(60)...')
    rps60 = get_sector_rps(date, 60)
    time.sleep(1.5)

    all_inds = set(rps10.keys()) & set(rps20.keys()) & set(rps60.keys())
    resonance = []
    for ind in all_inds:
        r10, r20, r60 = rps10[ind]['rps'], rps20[ind]['rps'], rps60[ind]['rps']
        if r10 >= 85 and r20 >= 85 and r60 >= 85:
            resonance.append({
                'industry': ind, 'rps10': r10, 'rps20': r20, 'rps60': r60,
                'avg_rps': round((r10 + r20 + r60) / 3, 1),
                'count10': rps10[ind]['count'], 'count20': rps20[ind]['count'], 'count60': rps60[ind]['count'],
            })

    resonance.sort(key=lambda x: -x['avg_rps'])

    log('  统计百日新高分布...')
    nh_data = get_100day_new_high_sectors(date)

    core_sectors = []
    for item in resonance:
        ind = item['industry']
        nh_count = nh_data.get(ind, {}).get('count', 0)
        item['new_high_count'] = nh_count
        if nh_count >= 3 or item['avg_rps'] >= 92:
            core_sectors.append(item)

    core_sectors.sort(key=lambda x: -x['new_high_count'])

    result = {
        'resonance_sectors': resonance[:20],
        'new_high_sectors': sorted(nh_data.items(), key=lambda x: -x[1]['count'])[:20],
        'core_sectors': core_sectors[:10],
    }

    log(f'  三线共振板块: {len(resonance)} 个')
    log(f'  核心主线板块: {len(core_sectors)} 个')
    for s in core_sectors[:5]:
        log(f'    {s["industry"]} (RPS: {s["avg_rps"]}/100, 新高: {s["new_high_count"]}只)')

    return result


# ═══════════════════════════════════════════════════
# 模块三：个股筛选
# ═══════════════════════════════════════════════════

def round1_breakout_pool(date, core_sectors=None, kcache=None):
    """第一轮：突破观察池"""
    log('[模块三-第一轮] 建立突破观察池...')

    params = {
        'limit': 300, 'excludeST': 'true',
        'aboveMa': [60], 'volumeRatioMin': 1.5,
        'recentNdChgDays': 20, 'recentNdChgMax': 25,
        'marketCapType': 'circ', 'marketCapMinYi': 20, 'marketCapMaxYi': 500,
        'sortBy': 'volumeRatio', 'sortOrder': 'desc', 'date': date,
    }
    try:
        stocks = get_stock_screener(params)
    except Exception as e:
        log(f'  [错误] 条件选股失败: {e}')
        return []

    if not stocks:
        log('  无符合条件的股票')
        return []

    # 批量预取 kline
    codes_to_fetch = [s.get('code', '') for s in stocks if s.get('code', '')]
    if kcache:
        kcache.fetch_batch(codes_to_fetch, 80)

    candidates = []
    for s in stocks:
        code = s.get('code', '')
        name = s.get('name', '')
        industry = s.get('industry', '') or ''
        ma60_stock = safe_float(s.get('ma60', 0))
        close = safe_float(s.get('close', 0))
        volume_ratio = safe_float(s.get('volumeRatio', 0))
        amount_yi = safe_float(s.get('amountYi', 0))
        mcap = safe_float(s.get('marketCapYi', 0))
        pct_chg = safe_float(s.get('closePctChg', 0))

        # 从缓存获取 kline
        klines = kcache.get(code, 80) if kcache else get_kline(code, 80) or []
        if len(klines) < 60:
            continue

        closes_k = [safe_float(k['close']) for k in klines]

        # MA60 方向
        ma60_vals = []
        for i in range(59, len(closes_k)):
            ma60_vals.append(sum(closes_k[i-59:i+1]) / 60)
        if len(ma60_vals) >= 5:
            if ma60_vals[-1] > ma60_vals[0]:
                ma60_dir = 'up'
            elif ma60_vals[-1] < ma60_vals[0] * 0.99:
                ma60_dir = 'down'
            else:
                ma60_dir = 'flat'
        else:
            ma60_dir = 'flat'

        if ma60_dir == 'down':
            continue

        # 核心板块过滤
        if core_sectors:
            in_core = any(cs['industry'] in industry for cs in core_sectors)
            if not in_core:
                continue

        # 找突破日期
        break_date = None
        for i in range(len(klines)-1, 1, -1):
            prev_c = safe_float(klines[i-1].get('close', 0))
            curr_c = safe_float(klines[i].get('close', 0))
            w = closes_k[max(0, i-59):i+1]
            if len(w) >= 60:
                m60 = sum(w) / 60
                if prev_c < m60 and curr_c > m60:
                    break_date = klines[i].get('date', '')
                    break

        candidates.append({
            'code': code, 'name': name, 'industry': industry,
            'close': close, 'pct_chg': pct_chg,
            'volume_ratio': volume_ratio, 'amount_yi': amount_yi,
            'market_cap_yi': mcap, 'ma60': ma60_stock,
            'ma60_dir': ma60_dir, 'break_date': break_date,
        })

    log(f'  突破观察池: {len(candidates)} 只')
    return candidates


def round2_pullback_confirm(candidates, date, kcache=None, core_sectors=None):
    """第二轮：回调确认——放量突破后缩量回踩支撑"""
    log('[模块三-第二轮] 筛选回调确认信号...')

    # 独立扫描池：核心板块 + 20-500亿 + 非ST + 在MA60上方
    # 不要求今日放量（应该缩量）
    scan_params = {
        'limit': 300, 'excludeST': 'true',
        'aboveMa': [60],
        'marketCapType': 'circ', 'marketCapMinYi': 20, 'marketCapMaxYi': 500,
        'recentNdChgDays': 20, 'recentNdChgMax': 30,
        'date': date,
    }
    if core_sectors:
        scan_params['conceptKeywords'] = [s['industry'][:4] for s in core_sectors[:3]]

    pool_stocks = []
    try:
        pool_stocks = get_stock_screener(scan_params)
    except:
        pass

    # 也加入候选池
    candidate_codes = list(set(c['code'] for c in candidates))
    for s in pool_stocks:
        code = s.get('code', '')
        if code and code not in candidate_codes:
            candidate_codes.append(code)

    log(f'  扫描 {len(candidate_codes)} 只候选股的回调形态...')

    # 批量预取所有 kline
    if kcache:
        kcache.fetch_batch(candidate_codes, 80)

    confirmed = []
    processed = 0

    for code in candidate_codes:
        processed += 1
        if processed % 50 == 0:
            log(f'  进度 {processed}/{len(candidate_codes)}...')

        klines = kcache.get(code, 80) if kcache else get_kline(code, 80) or []
        if len(klines) < 70:
            continue

        today_k = klines[-1]
        yesterday_k = klines[-2] if len(klines) >= 2 else None
        current_close = safe_float(today_k.get('close', 0))
        current_high = safe_float(today_k.get('high', 0))
        current_low = safe_float(today_k.get('low', 0))
        current_open = safe_float(today_k.get('open', 0))
        current_vol = safe_float(today_k.get('volume', 0))
        current_amount = safe_float(today_k.get('amount', 0))

        closes = [safe_float(k['close']) for k in klines]
        ma20 = calc_sma(closes, 20)
        ma60 = calc_sma(closes, 60)

        if not ma60 or current_close < ma60 * 0.98:
            continue

        # 找过去 3-15 天内的放量信号
        # 类型A: MA60 突破（prev<MA60, curr>MA60 + 放量）
        # 类型B: 在MA60上方放量拉升（continuation）
        break_idx = None
        break_type = None
        scan_end = min(len(klines) - 2, 17)

        for lookback in range(3, scan_end + 1):
            i = len(klines) - 1 - lookback
            if i < 60:
                continue
            curr_c_i = safe_float(klines[i].get('close', 0))
            prev_c_i = safe_float(klines[i-1].get('close', 0))
            vol_i = safe_float(klines[i].get('volume', 0))
            w = closes[i-59:i+1]
            if len(w) < 60:
                continue
            m60_i = sum(w) / 60
            avg_v = sum(safe_float(klines[j].get('volume', 0)) for j in range(max(0, i-5), i)) / 5

            # 类型A: MA60 突破 + 放量
            if avg_v > 0 and vol_i / avg_v >= 1.3 and prev_c_i < m60_i and curr_c_i > m60_i:
                break_idx = i
                break_type = 'A'
                break

            # 类型B: 在MA60上方放量拉升
            if (not break_idx) and avg_v > 0 and vol_i / avg_v >= 2.0 and curr_c_i > m60_i:
                break_idx = i
                break_type = 'B'

        if break_idx is None:
            continue

        # 回调判断
        post_high = max(safe_float(klines[j]['high']) for j in range(break_idx, len(klines)))
        pullback_pct = (post_high - current_close) / post_high * 100
        if pullback_pct < 1.0:
            continue

        # 缩量判断
        recent_vols = [safe_float(k['volume']) for k in klines[-10:]]
        max_vol_10d = max(recent_vols) if recent_vols else 0
        # 用最近3日均量对比近期峰量
        vol_avg_3d = sum(recent_vols[-3:]) / min(3, len(recent_vols)) if len(recent_vols) >= 1 else current_vol
        vol_shrink = vol_avg_3d / max_vol_10d if max_vol_10d > 0 else 1
        if vol_shrink > 0.75:
            continue

        # 支撑判断
        supports = []
        if ma20:
            supports.append(('MA20', ma20))
        if ma60:
            supports.append(('MA60', ma60))
        recent_avg = sum(closes[-10:]) / 10 if len(closes) >= 10 else 0
        if recent_avg:
            supports.append(('10日均', recent_avg))
        nearest_support = None
        min_dist = float('inf')
        for sn, sp in supports:
            d = abs(current_close - sp) / sp * 100 if sp > 0 else 999
            if d < min_dist:
                min_dist = d
                nearest_support = (sn, round(sp, 2), round(d, 1))

        # 止跌信号
        stop_signal = []
        body = abs(current_close - current_open)
        total_range = current_high - current_low if current_high > current_low else 1
        lower_shadow = min(current_close, current_open) - current_low

        if body > 0 and body / total_range < 0.35:
            stop_signal.append('小实体')
        if current_close > current_open and body / max(current_close, 0.01) < 0.04:
            stop_signal.append('小阳线')
        if lower_shadow > body * 2 and body > 0:
            stop_signal.append('长下影')
        if yesterday_k:
            pp = safe_float(yesterday_k.get('pct_chg', 0))
            cp = safe_float(today_k.get('pct_chg', 0))
            if pp < -1.5 and cp > pp:
                stop_signal.append('跌幅收窄')
            if pp < -2 and cp > 0:
                stop_signal.append('止跌翻红')

        if not stop_signal and yesterday_k and len(klines) >= 3:
            pp2 = safe_float(klines[-3].get('pct_chg', 0))
            pp = safe_float(yesterday_k.get('pct_chg', 0))
            cp = safe_float(today_k.get('pct_chg', 0))
            if pp2 < -1.5 and pp < -1.5 and cp > pp:
                stop_signal.append('连跌后企稳')

        if not stop_signal and vol_shrink < 0.4:
            stop_signal.append('极度缩量')
        if not stop_signal:
            continue

        c_info = next((c for c in candidates if c.get('code') == code), None)
        confirmed.append({
            'code': code,
            'name': c_info.get('name', '') if c_info else '',
            'industry': c_info.get('industry', '') if c_info else '',
            'current_close': round(current_close, 2),
            'pct_chg': round(safe_float(today_k.get('pct_chg', 0)), 2),
            'pullback_pct': round(pullback_pct, 1),
            'vol_shrink_ratio': round(vol_shrink, 2),
            'nearest_support': nearest_support,
            'stop_signals': ' + '.join(stop_signal),
            'ma60': round(ma60, 2) if ma60 else 0,
            'ma20': round(ma20, 2) if ma20 else 0,
            'amount_yi': round(current_amount / 1e8, 1) if current_amount else 0,
        })

    confirmed.sort(key=lambda x: x['vol_shrink_ratio'])
    log(f'  回调确认候选: {len(confirmed)} 只')
    return confirmed


# ═══════════════════════════════════════════════════
# 模块四：生成报告
# ═══════════════════════════════════════════════════

def generate_report(market_env, sector_data, breakout_pool, pullback_candidates):
    lines = []
    date_display = fmt_date(market_env['date'])
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    lines.append(f'# 每日选股简报 — {date_display}')
    lines.append(f'> 生成时间: {now}  |  数据源: 悟道API')
    lines.append('')
    lines.append('---')
    lines.append('')

    # 一、大盘环境
    lines.append('## 一、大盘环境判断')
    lines.append('')
    lines.append(f'- **市场状态**: {market_env["market_state"]}')
    lines.append(f'- **仓位上限**: {market_env["position_limit"]}')
    lines.append(f'- **操作建议**: {market_env["position_note"]}')
    lines.append(f'- **市场温度**: {market_env["market_temperature"]}°C')
    lines.append(f'- **涨跌比**: {market_env["rise_count"]}:{market_env["fall_count"]} (涨{market_env["rise_ratio"]}%)')
    lines.append('')

    # 二、主线板块
    lines.append('## 二、主线板块')
    lines.append('')
    core = sector_data.get('core_sectors', [])
    if core:
        lines.append('### 核心主线（RPS三线共振 + 百日新高交叉验证）')
        lines.append('')
        lines.append('| 板块 | RPS(10) | RPS(20) | RPS(60) | 均RPS | 百日新高数 |')
        lines.append('|------|---------|---------|---------|-------|-----------|')
        for s in core:
            lines.append(f'| {s["industry"]} | {s["rps10"]} | {s["rps20"]} | {s["rps60"]} | {s["avg_rps"]} | {s["new_high_count"]} |')
        lines.append('')

    resonance = sector_data.get('resonance_sectors', [])
    if resonance:
        lines.append('### 三线共振板块（RPS≥85）')
        lines.append('')
        lines.append('| 板块 | RPS(10) | RPS(20) | RPS(60) | 均RPS |')
        lines.append('|------|---------|---------|---------|-------|')
        for s in resonance[:15]:
            lines.append(f'| {s["industry"]} | {s["rps10"]} | {s["rps20"]} | {s["rps60"]} | {s["avg_rps"]} |')
        lines.append('')

    # 三、突破观察池
    lines.append('## 三、突破观察池')
    lines.append('')
    lines.append(f'> 共 {len(breakout_pool)} 只股票符合第一轮条件')
    lines.append('')
    if breakout_pool:
        lines.append('| 代码 | 名称 | 板块 | 收盘价 | 涨幅 | 量比 | 成交额(亿) | 流通市值(亿) | 突破日期 |')
        lines.append('|------|------|------|--------|------|------|-----------|-------------|---------|')
        for c in breakout_pool:
            bd = c.get('break_date', '') or 'N/A'
            if bd and len(str(bd)) == 8:
                bd = f'{str(bd)[:4]}-{str(bd)[4:6]}-{str(bd)[6:8]}'
            lines.append(f'| {c["code"]} | {c["name"]} | {c["industry"]} | {c["close"]} | {c["pct_chg"]:+.2f}% | {c["volume_ratio"]} | {c["amount_yi"]} | {c["market_cap_yi"]} | {bd} |')
        lines.append('')

    # 四、回调确认候选
    lines.append('## 四、回调确认候选')
    lines.append('')
    lines.append(f'> 共 {len(pullback_candidates)} 只股票符合第二轮条件')
    lines.append('')
    if pullback_candidates:
        lines.append('| 代码 | 名称 | 板块 | 当前价 | 涨幅 | 回调幅度 | 缩量比 | 最近支撑 | 止跌信号 |')
        lines.append('|------|------|------|--------|------|---------|-------|---------|---------|')
        for c in pullback_candidates:
            sup = c.get('nearest_support', ('', '', ''))
            sup_str = f'{sup[0]} {sup[1]} ({sup[2]}%)' if sup[0] else 'N/A'
            lines.append(f'| {c["code"]} | {c["name"]} | {c["industry"]} | {c["current_close"]} | {c["pct_chg"]:+.2f}% | {c["pullback_pct"]}% | {c["vol_shrink_ratio"]} | {sup_str} | {c["stop_signals"]} |')
        lines.append('')
        lines.append('### ⚠️ 重要提醒')
        lines.append('')
        for c in pullback_candidates:
            lines.append(f'- **{c["name"]}({c["code"]})**: 次日预警：请以次日开盘后确认形态为准，勿在尾盘买入。')
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('**风险提示**：本报告仅提供技术形态筛选参考，不构成投资建议。')
    lines.append('所有信号均需次日开盘后确认，请结合个人风险承受能力决策。')

    return '\n'.join(lines)


# ═══════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════

def run(date=None, output_file=None):
    date = parse_date(date)
    display_date = fmt_date(date)
    kcache = KlineCache()

    print('=' * 60)
    print(f'  每日选股系统 v1.0')
    print(f'  交易日: {display_date}')
    print('=' * 60)
    print()

    t0 = time.time()

    market_env = get_market_environment(date, kcache)
    print()

    if market_env['market_state'] == '下跌市':
        log('[跳过] 下跌市，跳过板块和个股筛选')
        report = generate_report(market_env, {'core_sectors': [], 'resonance_sectors': [], 'new_high_sectors': []}, [], [])
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            log(f'\n报告已保存: {output_file}')
        else:
            print(report)
        return

    sector_data = lock_main_sectors(date)
    print()

    core = sector_data.get('core_sectors', [])
    core_names = [s['industry'] for s in core]

    breakout_pool = round1_breakout_pool(date, core if core else None, kcache)
    print()

    pullback_candidates = round2_pullback_confirm(breakout_pool, date, kcache)
    print()

    report = generate_report(market_env, sector_data, breakout_pool, pullback_candidates)

    elapsed = time.time() - t0
    log(f'\n总用时: {elapsed:.1f}秒')

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)
        log(f'报告已保存: {output_file}')
    else:
        print('\n' + '=' * 60)
        print(report)

    json_path = os.path.join(DATA_DIR, f'选股结果_{date}.json')
    json.dump({
        'date': date,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'market_env': market_env,
        'sector_data': {
            'core_count': len(sector_data.get('core_sectors', [])),
            'resonance_count': len(sector_data.get('resonance_sectors', [])),
        },
        'breakout_pool_count': len(breakout_pool),
        'pullback_candidates_count': len(pullback_candidates),
    }, open(json_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    return report


def main():
    date = None
    output_file = None
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--date' and i + 1 < len(sys.argv):
            date = sys.argv[i + 1]; i += 2
        elif sys.argv[i] == '--output' and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]; i += 2
        else:
            i += 1
    run(date=date, output_file=output_file)

if __name__ == '__main__':
    main()
